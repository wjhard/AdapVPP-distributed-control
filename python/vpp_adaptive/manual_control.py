from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

from .models import LinkMetric, OperatingMode, QualitySnapshot
from .security import ZeroTrustSecurityManager


@dataclass
class PendingManualOperation:
    request_id: str
    operation: str
    target_key: str
    target: Dict[str, Any]
    selected_at_epoch_ms: int
    expires_at_epoch_ms: int
    selected_at_monotonic: float
    expires_at_monotonic: float


@dataclass
class ManualIntervention:
    kind: str
    target_key: str
    label: str
    started_at_elapsed_s: float
    expires_at_elapsed_s: float
    metadata: Dict[str, Any] = field(default_factory=dict)


class ManualControlManager:
    """IEC 61850-style Select-Cancel-Operate manager for manual interventions."""

    def __init__(
        self,
        security: ZeroTrustSecurityManager,
        execute_callback: Callable[[str, Dict[str, Any]], Dict[str, Any]],
        select_timeout_s: float = 30.0,
    ) -> None:
        self.security = security
        self.execute_callback = execute_callback
        self.select_timeout_s = select_timeout_s
        self.pending: Dict[str, PendingManualOperation] = {}
        self.active_link_faults: Dict[str, ManualIntervention] = {}
        self.active_storage_charge: ManualIntervention | None = None
        self.active_forced_mode: ManualIntervention | None = None
        self.recent_events: List[Dict[str, Any]] = []

    def handle_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        action = str(message.get("action", "")).lower()
        if action == "select":
            return self.select(str(message.get("operation", "")), dict(message.get("target") or {}))
        if action == "cancel":
            return self.cancel(str(message.get("request_id", "")), explicit=True)
        if action == "operate":
            return self.operate(str(message.get("request_id", "")))
        return self._response(False, "rejected", f"unknown manual control action: {action}")

    def select(self, operation: str, target: Dict[str, Any]) -> Dict[str, Any]:
        now = time.monotonic()
        self._expire_pending(now)
        target_key = self._target_key(operation, target)
        if target_key in self.pending:
            pending = self.pending[target_key]
            self._audit(
                "MANUAL_CONTROL_REJECTED",
                operation,
                target_key,
                "该操作正在等待确认，请稍后再试",
                {"request_id": pending.request_id},
            )
            return self._response(
                False,
                "rejected",
                "该操作正在等待确认，请稍后再试",
                pending=pending,
            )

        request_id = str(uuid.uuid4())
        epoch_ms = int(time.time() * 1000)
        pending = PendingManualOperation(
            request_id=request_id,
            operation=operation,
            target_key=target_key,
            target=target,
            selected_at_epoch_ms=epoch_ms,
            expires_at_epoch_ms=epoch_ms + int(self.select_timeout_s * 1000),
            selected_at_monotonic=now,
            expires_at_monotonic=now + self.select_timeout_s,
        )
        self.pending[target_key] = pending
        self._audit(
            "MANUAL_CONTROL_SELECTED",
            operation,
            target_key,
            "操作已选定，等待30秒内确认执行",
            {"request_id": request_id, "target": target},
        )
        return self._response(True, "selected", "已选定，等待确认执行", pending=pending)

    def cancel(self, request_id: str, explicit: bool) -> Dict[str, Any]:
        now = time.monotonic()
        self._expire_pending(now)
        pending = self._find_pending(request_id)
        if pending is None:
            return self._response(False, "not_found", "未找到待确认操作，可能已超时或已处理")
        self.pending.pop(pending.target_key, None)
        event_type = "MANUAL_CONTROL_CANCELLED" if explicit else "MANUAL_CONTROL_TIMEOUT_CANCELLED"
        reason = "操作员取消手动操作" if explicit else "30秒未确认，自动取消"
        self._audit(event_type, pending.operation, pending.target_key, reason, {"request_id": request_id})
        return self._response(True, "cancelled", reason)

    def operate(self, request_id: str) -> Dict[str, Any]:
        now = time.monotonic()
        self._expire_pending(now)
        pending = self._find_pending(request_id)
        if pending is None:
            return self._response(False, "not_found", "未找到待确认操作，可能已超时或已处理")
        self.pending.pop(pending.target_key, None)
        result = self.execute_callback(pending.operation, pending.target)
        ok = bool(result.get("ok", True))
        reason = str(result.get("message", "操作已执行" if ok else "操作执行失败"))
        self._audit(
            "MANUAL_CONTROL_OPERATED" if ok else "MANUAL_CONTROL_FAILED",
            pending.operation,
            pending.target_key,
            reason,
            {"request_id": request_id, "target": pending.target, "result": result},
        )
        return self._response(ok, "operated" if ok else "failed", reason)

    def activate_link_fault(self, link_key: str, duration_s: float, elapsed_s: float) -> None:
        self.active_link_faults[link_key] = ManualIntervention(
            kind="link_fault",
            target_key=f"link_fault:{link_key}",
            label=f"链路{link_key}手动故障",
            started_at_elapsed_s=elapsed_s,
            expires_at_elapsed_s=elapsed_s + max(1.0, float(duration_s)),
            metadata={"link_key": link_key, "duration_s": duration_s},
        )

    def activate_storage_charge(self, duration_s: float, elapsed_s: float) -> None:
        self.active_storage_charge = ManualIntervention(
            kind="storage_charge_test",
            target_key="storage_charge:bess5",
            label="储能优先充电测试",
            started_at_elapsed_s=elapsed_s,
            expires_at_elapsed_s=elapsed_s + max(1.0, float(duration_s)),
            metadata={"duration_s": duration_s},
        )

    def activate_forced_mode(self, mode: OperatingMode, duration_s: float, elapsed_s: float) -> None:
        self.active_forced_mode = ManualIntervention(
            kind="force_mode",
            target_key="force_mode",
            label=f"手动强制状态: {mode.value}",
            started_at_elapsed_s=elapsed_s,
            expires_at_elapsed_s=elapsed_s + max(1.0, float(duration_s)),
            metadata={"mode": mode.value, "duration_s": duration_s},
        )

    def forced_mode(self, elapsed_s: float) -> OperatingMode | None:
        self._expire_interventions(elapsed_s)
        if self.active_forced_mode is None:
            return None
        return OperatingMode(str(self.active_forced_mode.metadata["mode"]))

    def apply_quality_overrides(self, quality: QualitySnapshot) -> QualitySnapshot:
        self._expire_interventions(quality.elapsed_s)
        if not self.active_link_faults:
            return quality
        links = dict(quality.links)
        changed = False
        for link_key in self.active_link_faults:
            metric = links.get(link_key)
            if metric is None:
                continue
            links[link_key] = LinkMetric(
                metric.src,
                metric.dst,
                delay_ms=max(metric.delay_ms, 720.0),
                loss_rate=max(metric.loss_rate, 0.92),
                available=False,
                configured_delay_ms=metric.configured_delay_ms,
                configured_loss_rate=metric.configured_loss_rate,
                measured_rtt_ms=metric.measured_rtt_ms,
            )
            changed = True
        if not changed:
            return quality
        average_delay = sum(item.delay_ms for item in links.values()) / max(len(links), 1)
        max_loss = max((item.loss_rate for item in links.values()), default=0.0)
        return QualitySnapshot(
            quality.elapsed_s,
            links,
            average_delay,
            max_loss,
            real_network_measurement=quality.real_network_measurement,
        )

    def snapshot(self, elapsed_s: float | None = None) -> Dict[str, Any]:
        now = time.monotonic()
        self._expire_pending(now)
        if elapsed_s is not None:
            self._expire_interventions(elapsed_s)
        return {
            "select_timeout_s": self.select_timeout_s,
            "pending": [self._pending_dict(item) for item in self.pending.values()],
            "active_interventions": [self._intervention_dict(item) for item in self._active_interventions()],
            "recent_events": self.recent_events[-20:],
        }

    def _expire_pending(self, now: float) -> None:
        expired = [item for item in self.pending.values() if item.expires_at_monotonic <= now]
        for item in expired:
            self.pending.pop(item.target_key, None)
            self._audit(
                "MANUAL_CONTROL_TIMEOUT_CANCELLED",
                item.operation,
                item.target_key,
                "30秒未确认，自动取消",
                {"request_id": item.request_id},
            )

    def _expire_interventions(self, elapsed_s: float) -> None:
        self.active_link_faults = {
            key: item for key, item in self.active_link_faults.items() if item.expires_at_elapsed_s > elapsed_s
        }
        if self.active_storage_charge and self.active_storage_charge.expires_at_elapsed_s <= elapsed_s:
            self.active_storage_charge = None
        if self.active_forced_mode and self.active_forced_mode.expires_at_elapsed_s <= elapsed_s:
            self.active_forced_mode = None

    def _find_pending(self, request_id: str) -> PendingManualOperation | None:
        for item in self.pending.values():
            if item.request_id == request_id:
                return item
        return None

    def _active_interventions(self) -> List[ManualIntervention]:
        values = list(self.active_link_faults.values())
        if self.active_storage_charge is not None:
            values.append(self.active_storage_charge)
        if self.active_forced_mode is not None:
            values.append(self.active_forced_mode)
        return values

    def _audit(
        self,
        event_type: str,
        operation: str,
        target_key: str,
        reason: str,
        metadata: Dict[str, Any],
    ) -> None:
        payload = {
            "operation": operation,
            "target_key": target_key,
            **metadata,
        }
        self.security.record_event(event_type, None, reason, severity="INFO", metadata=payload)
        self.recent_events.append(
            {
                "event_type": event_type,
                "operation": operation,
                "target_key": target_key,
                "reason": reason,
                "timestamp_ms": int(time.time() * 1000),
            }
        )
        self.recent_events = self.recent_events[-40:]

    def _response(
        self,
        ok: bool,
        status: str,
        message: str,
        pending: PendingManualOperation | None = None,
    ) -> Dict[str, Any]:
        return {
            "message_type": "manual_control_response",
            "ok": ok,
            "status": status,
            "message": message,
            "pending": self._pending_dict(pending) if pending else None,
            "manual_control": self.snapshot(),
        }

    @staticmethod
    def _target_key(operation: str, target: Dict[str, Any]) -> str:
        if operation == "link_fault":
            return f"link_fault:{target.get('link_key', '')}"
        if operation == "storage_charge_test":
            return "storage_charge:bess5"
        if operation == "security_incident":
            return f"security_incident:node{target.get('node', '')}"
        if operation == "force_mode":
            return "force_mode"
        return f"{operation}:{target}"

    @staticmethod
    def _pending_dict(item: PendingManualOperation | None) -> Dict[str, Any] | None:
        if item is None:
            return None
        return {
            "request_id": item.request_id,
            "operation": item.operation,
            "target_key": item.target_key,
            "target": item.target,
            "selected_at_epoch_ms": item.selected_at_epoch_ms,
            "expires_at_epoch_ms": item.expires_at_epoch_ms,
        }

    @staticmethod
    def _intervention_dict(item: ManualIntervention) -> Dict[str, Any]:
        return {
            "kind": item.kind,
            "target_key": item.target_key,
            "label": item.label,
            "started_at_elapsed_s": round(item.started_at_elapsed_s, 3),
            "expires_at_elapsed_s": round(item.expires_at_elapsed_s, 3),
            "metadata": item.metadata,
        }
