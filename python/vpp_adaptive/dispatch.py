from __future__ import annotations

from typing import List, Sequence

from .controllers import ControllerManager
from .matlab_backend import MatlabDispatchBackend
from .models import DispatchResult, OperatingMode, QualitySnapshot, ResourceSnapshot


class AdaptiveDispatcher:
    """Run dispatch controllers and apply bumpless output transitions."""

    def __init__(
        self,
        backend: MatlabDispatchBackend,
        ramp_rate_mw_per_s: float = 2.5,
        force_storage_charge_test: bool = False,
    ) -> None:
        self.backend = backend
        self.ramp_rate_mw_per_s = ramp_rate_mw_per_s
        self.previous_command = [0.0, 0.0, 0.0, 0.0, 0.0]
        self.installed_pmax = [50.0, 40.0, 60.0, 55.0, 30.0]
        self.installed_pmin = [0.0, 0.0, 0.0, 0.0, -30.0]
        self.controller_manager = ControllerManager(
            backend,
            force_storage_charge_test=force_storage_charge_test,
        )

    def dispatch(
        self,
        mode: OperatingMode,
        quality: QualitySnapshot,
        clusters: List[List[int]],
        resource: ResourceSnapshot,
        interval_s: float,
        renewable_pmax: Sequence[float] | None = None,
    ) -> DispatchResult:
        previous = list(self.previous_command)
        controller_result = self.controller_manager.run(
            mode=mode,
            quality=quality,
            clusters=clusters,
            resource=resource,
            previous_command=previous,
            installed_pmin=self.installed_pmin,
            installed_pmax=self.installed_pmax,
            renewable_pmax=renewable_pmax,
        )

        command = self._smooth(previous, controller_result.target_mw, interval_s)
        self.previous_command = command
        self.controller_manager.observe_command(command, interval_s)
        max_delta = max(abs(a - b) for a, b in zip(command, previous))
        return DispatchResult(
            mode,
            controller_result.target_mw,
            command,
            previous,
            max_delta,
            clusters,
            controller_result.backend,
            controller_result.note,
            controller_result.active_controllers,
            controller_result.controller_trace,
            controller_result.dispatch_sources,
        )

    def _smooth(self, previous: Sequence[float], target: Sequence[float], interval_s: float) -> List[float]:
        max_step = self.ramp_rate_mw_per_s * max(interval_s, 1e-6)
        smoothed: List[float] = []
        for old, new in zip(previous, target):
            delta = min(max(new - old, -max_step), max_step)
            smoothed.append(old + delta)
        return smoothed
