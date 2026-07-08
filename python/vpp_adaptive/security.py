from __future__ import annotations

import hmac
import json
import hashlib
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Deque, Dict, Iterable, List


NODE_CAPACITY_MW = {
    1: 50.0,
    2: 40.0,
    3: 60.0,
    4: 55.0,
    5: 30.0,
}

NODE_IDENTITIES = {
    1: ("node-1-pv", "adapvpp-node-1-hmac-demo-key"),
    2: ("node-2-pv", "adapvpp-node-2-hmac-demo-key"),
    3: ("node-3-wind", "adapvpp-node-3-hmac-demo-key"),
    4: ("node-4-wind", "adapvpp-node-4-hmac-demo-key"),
    5: ("node-5-bess", "adapvpp-node-5-hmac-demo-key"),
}

MASTER_ACTOR = "state_machine_master"


@dataclass(frozen=True)
class SecurityEvent:
    timestamp: str
    event_type: str
    severity: str
    node: int | None
    reason: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NodeTrustState:
    node: int
    identity: str
    score: float = 100.0
    auth_failures: int = 0
    invalid_reports: int = 0
    jump_alerts: int = 0
    accepted_messages: int = 0
    last_auth_ok: bool = True
    low_trust: bool = False
    recent_values: Deque[float] = field(default_factory=lambda: deque(maxlen=8))
    recent_alerts: Deque[str] = field(default_factory=lambda: deque(maxlen=5))


class SecurityAuditLogger:
    """Dedicated zero-trust security audit log, separate from runtime telemetry."""

    def __init__(self, project_root: Path) -> None:
        log_dir = project_root / "logs" / "security_audit"
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.text_path = log_dir / f"security_audit_{stamp}.log"
        self.jsonl_path = log_dir / f"security_audit_{stamp}.jsonl"

    def write(self, event: SecurityEvent) -> None:
        line = (
            f"{event.timestamp} {event.severity} {event.event_type} "
            f"node={event.node if event.node is not None else '-'} reason={event.reason} "
            f"metadata={event.metadata}"
        )
        with self.text_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        with self.jsonl_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event.__dict__, ensure_ascii=False, separators=(",", ":")) + "\n")


class ZeroTrustSecurityManager:
    """Authenticate every data-plane message and continuously score node trust."""

    def __init__(self, project_root: Path, low_trust_threshold: float = 60.0) -> None:
        self.low_trust_threshold = low_trust_threshold
        self.audit = SecurityAuditLogger(project_root)
        self.node_states: Dict[int, NodeTrustState] = {
            node: NodeTrustState(node=node, identity=identity)
            for node, (identity, _key) in NODE_IDENTITIES.items()
        }
        self.recent_events: Deque[SecurityEvent] = deque(maxlen=20)
        self._control_denials_seen: set[tuple[str, str]] = set()
        self.record_event(
            "ZERO_TRUST_READY",
            None,
            "零信任节点认证与持续信任评估已启用",
            severity="INFO",
            metadata={"nodes": list(NODE_IDENTITIES)},
        )

    def sign_node_message(self, node: int, message: Dict[str, Any]) -> Dict[str, Any]:
        identity, key = NODE_IDENTITIES[node]
        envelope = {
            "identity": identity,
            "message": message,
            "mac": self._mac(key, message),
        }
        return envelope

    def verify_node_message(self, envelope: Dict[str, Any]) -> tuple[bool, Dict[str, Any] | None, str]:
        message = envelope.get("message")
        if not isinstance(message, dict):
            self._record_auth_failure(None, "消息缺少有效message字段", {"envelope": envelope})
            return False, None, "missing message"

        claimed_node = self._node_from_message(message)
        if claimed_node not in NODE_IDENTITIES:
            self._record_auth_failure(claimed_node, "未知节点身份", {"message": message})
            return False, None, "unknown node"

        identity, key = NODE_IDENTITIES[claimed_node]
        if envelope.get("identity") != identity:
            self._record_auth_failure(
                claimed_node,
                "身份标识与声明节点不匹配",
                {"expected_identity": identity, "actual_identity": envelope.get("identity")},
            )
            return False, None, "identity mismatch"

        expected = self._mac(key, message)
        actual = str(envelope.get("mac", ""))
        if not hmac.compare_digest(expected, actual):
            self._record_auth_failure(claimed_node, "HMAC签名验证失败，消息可能被伪造或篡改", {})
            return False, None, "bad mac"

        state = self.node_states[claimed_node]
        state.accepted_messages += 1
        state.last_auth_ok = True
        self._recover_trust(claimed_node, 0.12)
        return True, message, "ok"

    def observe_node_report(self, node: int, reported_mw: float, elapsed_s: float, context: str) -> None:
        state = self.node_states[node]
        capacity = NODE_CAPACITY_MW[node]
        value = float(reported_mw)
        if node <= 4 and (value < -1e-6 or value > capacity * 1.05):
            self._penalize_node(
                node,
                18.0,
                "PHYSICAL_LIMIT_VIOLATION",
                f"节点上报出力{value:.2f}MW超出物理范围[0,{capacity:.1f}]MW",
                {"reported_mw": value, "capacity_mw": capacity, "elapsed_s": elapsed_s, "context": context},
            )
            state.invalid_reports += 1
        if node == 5 and abs(value) > capacity * 1.05:
            self._penalize_node(
                node,
                18.0,
                "PHYSICAL_LIMIT_VIOLATION",
                f"BESS上报功率{value:.2f}MW超出双向容量{capacity:.1f}MW",
                {"reported_mw": value, "capacity_mw": capacity, "elapsed_s": elapsed_s, "context": context},
            )
            state.invalid_reports += 1

        if state.recent_values:
            previous = state.recent_values[-1]
            jump = abs(value - previous)
            jump_threshold = max(12.0, capacity * 0.35)
            if jump > jump_threshold:
                state.jump_alerts += 1
                self._penalize_node(
                    node,
                    10.0,
                    "TREND_JUMP_ALERT",
                    f"节点上报出力从{previous:.2f}MW跳变到{value:.2f}MW，超过阈值{jump_threshold:.2f}MW",
                    {
                        "previous_mw": previous,
                        "reported_mw": value,
                        "jump_mw": jump,
                        "threshold_mw": jump_threshold,
                        "elapsed_s": elapsed_s,
                        "context": context,
                    },
                )
        state.recent_values.append(value)

    def require_control_actor(self, actor: str, interface: str, metadata: Dict[str, Any] | None = None) -> None:
        if actor == MASTER_ACTOR:
            return
        key = (actor, interface)
        if key not in self._control_denials_seen:
            self._control_denials_seen.add(key)
            self.record_event(
                "CONTROL_ACCESS_DENIED",
                None,
                f"拒绝非主控进程访问控制面接口: actor={actor}, interface={interface}",
                severity="HIGH",
                metadata=metadata or {},
            )
        raise PermissionError(f"unauthorized control-plane actor: {actor} -> {interface}")

    def apply_trust_weights(self, values: Iterable[float]) -> List[float]:
        adjusted: List[float] = []
        for index, value in enumerate(values, start=1):
            score = self.node_states[index].score
            weight = 1.0 if score >= self.low_trust_threshold else max(0.25, score / 100.0)
            adjusted.append(float(value) * weight)
        return adjusted

    def snapshot(self) -> Dict[str, Any]:
        nodes = []
        for node in sorted(self.node_states):
            state = self.node_states[node]
            nodes.append(
                {
                    "node": node,
                    "identity": state.identity,
                    "authentication_status": (
                        "异常" if state.low_trust or state.auth_failures > 0 or not state.last_auth_ok else "正常"
                    ),
                    "trust_score": round(state.score, 2),
                    "low_trust": state.low_trust,
                    "accepted_messages": state.accepted_messages,
                    "auth_failures": state.auth_failures,
                    "invalid_reports": state.invalid_reports,
                    "jump_alerts": state.jump_alerts,
                    "recent_alerts": list(state.recent_alerts),
                }
            )
        return {
            "zero_trust_enabled": True,
            "low_trust_threshold": self.low_trust_threshold,
            "audit_log_path": str(self.audit.text_path),
            "audit_jsonl_path": str(self.audit.jsonl_path),
            "nodes": nodes,
            "recent_events": [
                {
                    "timestamp": event.timestamp,
                    "event_type": event.event_type,
                    "severity": event.severity,
                    "node": event.node,
                    "reason": event.reason,
                    "metadata": event.metadata,
                }
                for event in self.recent_events
            ],
        }

    def diagnostic_lines(self) -> List[str]:
        low_trust_nodes = [node for node, state in self.node_states.items() if state.low_trust]
        return [
            "ZERO_TRUST_SECURITY enabled=true hmac=sha256 trust_model=continuous",
            f"SECURITY_AUDIT_LOG {self.audit.text_path}",
            f"LOW_TRUST_NODES {low_trust_nodes if low_trust_nodes else 'none'}",
            *[
                "  "
                + f"node {node}: identity={state.identity} score={state.score:.1f} "
                + f"auth_failures={state.auth_failures} invalid_reports={state.invalid_reports} "
                + f"low_trust={state.low_trust}"
                for node, state in sorted(self.node_states.items())
            ],
        ]

    def simulate_formula_incident(self, kind: str, node: int, elapsed_s: float) -> None:
        if kind == "forged":
            self._record_auth_failure(node, "公式路径测试注入: 伪造身份消息", {"elapsed_s": elapsed_s})
        elif kind == "anomalous":
            self.observe_node_report(
                node,
                NODE_CAPACITY_MW[node] * 1.6,
                elapsed_s,
                "formula security incident injection",
            )
        elif kind == "control":
            try:
                self.require_control_actor(f"node_{node}", "matlab.et_admm_robust", {"elapsed_s": elapsed_s})
            except PermissionError:
                pass

    def record_event(
        self,
        event_type: str,
        node: int | None,
        reason: str,
        severity: str = "INFO",
        metadata: Dict[str, Any] | None = None,
    ) -> None:
        event = SecurityEvent(
            timestamp=datetime.now().isoformat(timespec="milliseconds"),
            event_type=event_type,
            severity=severity,
            node=node,
            reason=reason,
            metadata=metadata or {},
        )
        self.recent_events.append(event)
        self.audit.write(event)

    def _record_auth_failure(self, node: int | None, reason: str, metadata: Dict[str, Any]) -> None:
        if node in self.node_states:
            state = self.node_states[node]
            state.auth_failures += 1
            state.last_auth_ok = False
            self._penalize_node(node, 45.0, "AUTHENTICATION_FAILED", reason, metadata)
            if state.auth_failures >= 3:
                self._penalize_node(
                    node,
                    8.0,
                    "REPEATED_AUTH_FAILURES",
                    f"节点签名失败次数达到{state.auth_failures}次",
                    metadata,
                )
        else:
            self.record_event("AUTHENTICATION_FAILED", node, reason, severity="HIGH", metadata=metadata)

    def _penalize_node(
        self,
        node: int,
        points: float,
        event_type: str,
        reason: str,
        metadata: Dict[str, Any],
    ) -> None:
        state = self.node_states[node]
        state.score = max(0.0, state.score - points)
        state.recent_alerts.append(reason)
        severity = "HIGH" if state.score < self.low_trust_threshold else "MEDIUM"
        self.record_event(event_type, node, reason, severity=severity, metadata=metadata)
        if state.score < self.low_trust_threshold and not state.low_trust:
            state.low_trust = True
            self.record_event(
                "LOW_TRUST_NODE_ISOLATED",
                node,
                f"节点信任评分降至{state.score:.1f}，后续调度降低其数据采信权重",
                severity="HIGH",
                metadata={"trust_score": state.score, "threshold": self.low_trust_threshold},
            )

    def _recover_trust(self, node: int, points: float) -> None:
        state = self.node_states[node]
        if state.score < 100.0 and state.last_auth_ok:
            state.score = min(100.0, state.score + points)
            if state.low_trust and state.score >= self.low_trust_threshold + 8.0:
                state.low_trust = False
                self.record_event(
                    "LOW_TRUST_NODE_RECOVERED",
                    node,
                    f"节点信任评分恢复至{state.score:.1f}",
                    severity="INFO",
                    metadata={"trust_score": state.score},
                )

    @staticmethod
    def _node_from_message(message: Dict[str, Any]) -> int | None:
        if "src" in message:
            try:
                return int(message["src"])
            except Exception:
                return None
        return None

    @staticmethod
    def _canonical(message: Dict[str, Any]) -> bytes:
        return json.dumps(message, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

    def _mac(self, key: str, message: Dict[str, Any]) -> str:
        return hmac.new(key.encode("utf-8"), self._canonical(message), hashlib.sha256).hexdigest()
