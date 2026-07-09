from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
from typing import Dict, List

from .clustering import ConnectivityClusterer
from .dispatch import AdaptiveDispatcher
from .forecasting import ShortTermRenewableForecaster
from .link_quality import LinkQualitySimulator
from .manual_control import ManualControlManager
from .matlab_backend import MatlabDispatchBackend
from .models import DispatchResult, ForecastSnapshot, MODE_LABELS, OperatingMode, QualitySnapshot, StateDecision
from .resource_profile import ResourceProfile
from .runtime_logging import RunLogger
from .security import ZeroTrustSecurityManager
from .state_machine import AdaptiveStateMachine
from .toxiproxy_network import ToxiproxyLinkQualitySource
from .websocket_server import TelemetryWebSocketServer


class AdaptiveVppDemo:
    def __init__(
        self,
        project_root: Path,
        duration_s: float = 120.0,
        interval_s: float = 1.0,
        websocket_host: str = "127.0.0.1",
        websocket_port: int = 8765,
        realtime: bool = True,
        use_toxiproxy: bool = False,
        toxiproxy_api_port: int = 8474,
        force_bad_link: str | None = None,
        force_bad_start_s: float = 35.0,
        force_bad_duration_s: float = 12.0,
        force_storage_charge_test: bool = False,
        security_incident: str = "none",
        security_incident_at_s: float = 8.0,
        security_incident_node: int = 3,
    ) -> None:
        self.project_root = project_root
        self.duration_s = duration_s
        self.interval_s = interval_s
        self.realtime = realtime
        self.use_toxiproxy = use_toxiproxy

        self.run_logger = RunLogger(project_root)
        self.security = ZeroTrustSecurityManager(project_root)
        self.security_incident = security_incident
        self.security_incident_at_s = security_incident_at_s
        self.security_incident_node = security_incident_node
        self._formula_security_incident_sent = False
        if use_toxiproxy:
            self.link_quality = ToxiproxyLinkQualitySource(
                project_root=project_root,
                cycle_s=duration_s,
                api_port=toxiproxy_api_port,
                force_bad_link=force_bad_link,
                force_bad_start_s=force_bad_start_s,
                force_bad_duration_s=force_bad_duration_s,
                security=self.security,
                security_incident=security_incident,
                security_incident_at_s=security_incident_at_s,
                security_incident_node=security_incident_node,
            )
        else:
            self.link_quality = LinkQualitySimulator(cycle_s=duration_s)
        self.state_machine = AdaptiveStateMachine(min_dwell_s=3.0)
        self.clusterer = ConnectivityClusterer()
        self.resources = ResourceProfile(project_root)
        self.forecaster = ShortTermRenewableForecaster(project_root)
        self.backend = MatlabDispatchBackend(project_root, security=self.security)
        self.dispatcher = AdaptiveDispatcher(
            self.backend,
            force_storage_charge_test=force_storage_charge_test,
        )
        self.current_elapsed_s = 0.0
        self.effective_mode = OperatingMode.GLOBAL
        self.manual_control = ManualControlManager(self.security, self._execute_manual_operation)
        self.websocket = TelemetryWebSocketServer(
            websocket_host,
            websocket_port,
            on_message=self._handle_websocket_message,
        )
        self.visited_modes: List[OperatingMode] = [OperatingMode.GLOBAL]

    async def run(self) -> None:
        await self.websocket.start()
        if self.websocket.enabled:
            self.run_logger.info(f"WEBSOCKET_STATUS enabled ws://{self.websocket.host}:{self.websocket.port}")
        else:
            self.run_logger.info(f"WEBSOCKET_STATUS disabled reason={self.websocket.error}")
        self.run_logger.backend_status(self.backend.label)
        await self._start_link_quality_source()

        link_diagnostics: List[str] = []
        try:
            try:
                total_steps = int(self.duration_s / self.interval_s) + 1
                for step in range(total_steps):
                    elapsed_s = min(step * self.interval_s, self.duration_s)
                    self.current_elapsed_s = elapsed_s
                    quality = await self._sample_quality(elapsed_s)
                    quality = self.manual_control.apply_quality_overrides(quality)
                    auto_decision = self.state_machine.update(
                        elapsed_s,
                        quality.average_delay_ms,
                        quality.max_loss_rate,
                    )
                    decision = self._apply_manual_mode_override(elapsed_s, auto_decision)
                    if decision.changed:
                        self.visited_modes.append(decision.mode)

                    clusters = self._clusters_for_mode(decision.mode, quality)
                    actual_resource = self.resources.sample(elapsed_s, self.duration_s)
                    forecast = self.forecaster.update(elapsed_s, actual_resource)
                    dispatch_resource = self.forecaster.forecast_resource(actual_resource, forecast)
                    self._maybe_inject_formula_security_incident(elapsed_s)
                    forecast_pmax = self.security.apply_trust_weights(
                        self.forecaster.forecast_pmax(forecast)
                    )
                    dispatch = self.dispatcher.dispatch(
                        decision.mode,
                        quality,
                        clusters,
                        dispatch_resource,
                        self.interval_s,
                        renewable_pmax=forecast_pmax,
                    )

                    if decision.changed:
                        self.run_logger.transition(decision, quality, dispatch)
                    security_snapshot = self.security.snapshot()
                    manual_snapshot = self.manual_control.snapshot(elapsed_s)
                    self.run_logger.snapshot(
                        quality,
                        decision,
                        dispatch,
                        forecast,
                        security_snapshot,
                        manual_snapshot,
                    )
                    await self.websocket.broadcast(
                        self._payload(
                            quality,
                            decision,
                            dispatch,
                            forecast,
                            security_snapshot,
                            manual_snapshot,
                        )
                    )

                    if self.realtime and step < total_steps - 1:
                        await asyncio.sleep(self.interval_s)
            finally:
                await self.websocket.stop()

            link_diagnostics = self.link_quality.diagnostic_lines()
        finally:
            await self._stop_link_quality_source()

        self.run_logger.info(
            "DEMO_COMPLETE visited_modes="
            + "->".join(mode.name for mode in self.visited_modes)
        )
        for line in link_diagnostics:
            self.run_logger.info(line)
        for line in self.security.diagnostic_lines():
            self.run_logger.info(line)
        self.run_logger.print_key_fragments()
        print("\nVisited modes:", " -> ".join(MODE_LABELS[mode] for mode in self.visited_modes))
        title = "Toxiproxy measured link diagnostics" if self.use_toxiproxy else "Gilbert-Elliott link diagnostics"
        print(f"\n=== {title} ===")
        for line in link_diagnostics:
            print(line)
        print("\n=== Zero-trust security diagnostics ===")
        for line in self.security.diagnostic_lines():
            print(line)

    async def _start_link_quality_source(self) -> None:
        start = getattr(self.link_quality, "start", None)
        if start is None:
            return
        result = start(self.run_logger.info)
        if inspect.isawaitable(result):
            await result

    async def _stop_link_quality_source(self) -> None:
        stop = getattr(self.link_quality, "stop", None)
        if stop is None:
            return
        result = stop()
        if inspect.isawaitable(result):
            await result

    async def _sample_quality(self, elapsed_s: float) -> QualitySnapshot:
        result = self.link_quality.sample(elapsed_s)
        if inspect.isawaitable(result):
            return await result
        return result

    def _apply_manual_mode_override(
        self,
        elapsed_s: float,
        auto_decision: StateDecision,
    ) -> StateDecision:
        forced_mode = self.manual_control.forced_mode(elapsed_s)
        next_mode = forced_mode or auto_decision.mode
        changed = next_mode != self.effective_mode
        if forced_mode is not None:
            reason = f"manual_force_mode:{forced_mode.value}"
        elif changed:
            reason = f"manual_force_released:auto_mode={auto_decision.mode.value}"
        else:
            reason = auto_decision.reason
        decision = StateDecision(
            previous_mode=self.effective_mode,
            mode=next_mode,
            changed=changed,
            reason=reason,
            dwell_s=auto_decision.dwell_s,
        )
        self.effective_mode = next_mode
        return decision

    def _clusters_for_mode(self, mode: OperatingMode, quality: QualitySnapshot) -> List[List[int]]:
        if mode == OperatingMode.GLOBAL:
            return [[1, 2, 3, 4, 5]]
        if mode == OperatingMode.AUTONOMOUS:
            return [[1], [2], [3], [4], [5]]
        return self.clusterer.connected_components(quality)

    def _maybe_inject_formula_security_incident(self, elapsed_s: float) -> None:
        if (
            self.use_toxiproxy
            or self.security_incident == "none"
            or self._formula_security_incident_sent
            or elapsed_s < self.security_incident_at_s
        ):
            return
        self._formula_security_incident_sent = True
        self.security.simulate_formula_incident(
            self.security_incident,
            self.security_incident_node,
            elapsed_s,
        )

    def _handle_websocket_message(self, message: Dict[str, object]) -> Dict[str, object]:
        if message.get("message_type") != "manual_control":
            return {
                "message_type": "manual_control_response",
                "ok": False,
                "status": "rejected",
                "message": "unsupported websocket command type",
                "manual_control": self.manual_control.snapshot(self.current_elapsed_s),
            }
        return self.manual_control.handle_message(message)

    def _execute_manual_operation(self, operation: str, target: Dict[str, object]) -> Dict[str, object]:
        try:
            if operation == "link_fault":
                link_key = str(target.get("link_key", ""))
                duration_s = float(target.get("duration_s", 20.0))
                self.manual_control.activate_link_fault(link_key, duration_s, self.current_elapsed_s)
                force_runtime = getattr(self.link_quality, "force_bad_link_runtime", None)
                if callable(force_runtime):
                    force_runtime(link_key, duration_s, self.current_elapsed_s)
                return {
                    "ok": True,
                    "message": f"link fault active: {link_key}, duration={duration_s:.1f}s",
                }

            if operation == "storage_charge_test":
                duration_s = float(target.get("duration_s", 15.0))
                self.manual_control.activate_storage_charge(duration_s, self.current_elapsed_s)
                self.dispatcher.controller_manager.force_storage_charge_for(
                    self.current_elapsed_s,
                    duration_s,
                )
                return {
                    "ok": True,
                    "message": f"storage priority charge test active for {duration_s:.1f}s",
                }

            if operation == "security_incident":
                node = int(target.get("node", 3))
                kind = str(target.get("kind", "forged"))
                inject_runtime = getattr(self.link_quality, "inject_security_incident_runtime", None)
                if callable(inject_runtime):
                    inject_runtime(kind, node, self.current_elapsed_s)
                else:
                    self.security.simulate_formula_incident(kind, node, self.current_elapsed_s)
                return {
                    "ok": True,
                    "message": f"security incident injected: kind={kind}, node={node}",
                }

            if operation == "force_mode":
                mode = OperatingMode(str(target.get("mode", OperatingMode.GLOBAL.value)))
                duration_s = float(target.get("duration_s", 30.0))
                self.manual_control.activate_forced_mode(mode, duration_s, self.current_elapsed_s)
                return {
                    "ok": True,
                    "message": f"mode force active: {mode.value}, duration={duration_s:.1f}s",
                }
        except Exception as exc:
            return {"ok": False, "message": f"manual operation failed: {exc}"}

        return {"ok": False, "message": f"unknown manual operation: {operation}"}

    @staticmethod
    def _payload(
        quality: QualitySnapshot,
        decision: StateDecision,
        dispatch: DispatchResult,
        forecast: ForecastSnapshot,
        security: Dict[str, object],
        manual_control: Dict[str, object],
    ) -> Dict[str, object]:
        return {
            "elapsed_s": round(quality.elapsed_s, 3),
            "mode": decision.mode.value,
            "mode_label": MODE_LABELS[decision.mode],
            "average_delay_ms": round(quality.average_delay_ms, 3),
            "max_loss_rate": round(quality.max_loss_rate, 5),
            "real_network_measurement": quality.real_network_measurement,
            "links": quality.compact_links(),
            "clusters": dispatch.clusters,
            "security": security,
            "manual_control": manual_control,
            "forecast": {
                "method": forecast.method,
                "horizon_minutes": round(forecast.horizon_minutes, 3),
                "horizon_steps": forecast.horizon_steps,
                "dispatch_uses_forecast": forecast.dispatch_uses_forecast,
                "actual_mw": [round(x, 3) for x in forecast.actual_mw],
                "forecast_mw": [round(x, 3) for x in forecast.forecast_mw],
                "verified_forecast_mw": (
                    [round(x, 3) for x in forecast.verified_forecast_mw]
                    if forecast.verified_forecast_mw is not None
                    else None
                ),
                "rmse_mw": round(forecast.rmse_mw, 5),
                "mape_percent": round(forecast.mape_percent, 5),
                "per_node_rmse_mw": [round(x, 5) for x in forecast.per_node_rmse_mw],
                "per_node_mape_percent": [round(x, 5) for x in forecast.per_node_mape_percent],
                "sample_count": forecast.sample_count,
                "history_path": forecast.history_path,
            },
            "dispatch": {
                "target_mw": [round(x, 3) for x in dispatch.target_mw],
                "command_mw": [round(x, 3) for x in dispatch.command_mw],
                "max_delta_mw": round(dispatch.max_delta_mw, 5),
                "backend": dispatch.backend,
                "note": dispatch.note,
                "active_controllers": dispatch.active_controllers,
                "controller_trace": [
                    {
                        "controller": item.controller,
                        "controller_key": item.controller_key,
                        "priority": item.priority,
                        "action": item.action,
                        "reason": item.reason,
                        "nodes": item.nodes,
                    }
                    for item in dispatch.controller_trace
                ],
                "dispatch_sources": [
                    {
                        "node": item.node,
                        "controller": item.controller,
                        "controller_key": item.controller_key,
                        "priority": item.priority,
                        "reason": item.reason,
                        "overridden": item.overridden,
                        "previous_controller": item.previous_controller,
                        "previous_value_mw": (
                            round(item.previous_value_mw, 3)
                            if item.previous_value_mw is not None
                            else None
                        ),
                        "override_reason": item.override_reason,
                    }
                    for item in dispatch.dispatch_sources
                ],
            },
        }
