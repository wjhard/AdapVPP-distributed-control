from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
from typing import Dict, List

from .clustering import ConnectivityClusterer
from .dispatch import AdaptiveDispatcher
from .forecasting import ShortTermRenewableForecaster
from .link_quality import LinkQualitySimulator
from .matlab_backend import MatlabDispatchBackend
from .models import DispatchResult, ForecastSnapshot, MODE_LABELS, OperatingMode, QualitySnapshot, StateDecision
from .resource_profile import ResourceProfile
from .runtime_logging import RunLogger
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
    ) -> None:
        self.project_root = project_root
        self.duration_s = duration_s
        self.interval_s = interval_s
        self.realtime = realtime
        self.use_toxiproxy = use_toxiproxy

        self.run_logger = RunLogger(project_root)
        if use_toxiproxy:
            self.link_quality = ToxiproxyLinkQualitySource(
                project_root=project_root,
                cycle_s=duration_s,
                api_port=toxiproxy_api_port,
                force_bad_link=force_bad_link,
                force_bad_start_s=force_bad_start_s,
                force_bad_duration_s=force_bad_duration_s,
            )
        else:
            self.link_quality = LinkQualitySimulator(cycle_s=duration_s)
        self.state_machine = AdaptiveStateMachine(min_dwell_s=3.0)
        self.clusterer = ConnectivityClusterer()
        self.resources = ResourceProfile(project_root)
        self.forecaster = ShortTermRenewableForecaster(project_root)
        self.backend = MatlabDispatchBackend(project_root)
        self.dispatcher = AdaptiveDispatcher(self.backend)
        self.websocket = TelemetryWebSocketServer(websocket_host, websocket_port)
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
                    quality = await self._sample_quality(elapsed_s)
                    decision = self.state_machine.update(elapsed_s, quality.average_delay_ms, quality.max_loss_rate)
                    if decision.changed:
                        self.visited_modes.append(decision.mode)

                    clusters = self._clusters_for_mode(decision.mode, quality)
                    actual_resource = self.resources.sample(elapsed_s, self.duration_s)
                    forecast = self.forecaster.update(elapsed_s, actual_resource)
                    dispatch_resource = self.forecaster.forecast_resource(actual_resource, forecast)
                    forecast_pmax = self.forecaster.forecast_pmax(forecast)
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
                    self.run_logger.snapshot(quality, decision, dispatch, forecast)
                    await self.websocket.broadcast(self._payload(quality, decision, dispatch, forecast))

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
        self.run_logger.print_key_fragments()
        print("\nVisited modes:", " -> ".join(MODE_LABELS[mode] for mode in self.visited_modes))
        title = "Toxiproxy measured link diagnostics" if self.use_toxiproxy else "Gilbert-Elliott link diagnostics"
        print(f"\n=== {title} ===")
        for line in link_diagnostics:
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

    def _clusters_for_mode(self, mode: OperatingMode, quality: QualitySnapshot) -> List[List[int]]:
        if mode == OperatingMode.GLOBAL:
            return [[1, 2, 3, 4, 5]]
        if mode == OperatingMode.AUTONOMOUS:
            return [[1], [2], [3], [4], [5]]
        return self.clusterer.connected_components(quality)

    @staticmethod
    def _payload(
        quality: QualitySnapshot,
        decision: StateDecision,
        dispatch: DispatchResult,
        forecast: ForecastSnapshot,
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
            },
        }
