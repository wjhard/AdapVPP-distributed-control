from __future__ import annotations

from typing import List, Sequence

from .matlab_backend import MatlabDispatchBackend
from .models import DispatchResult, OperatingMode, QualitySnapshot, ResourceSnapshot
from .resource_profile import ResourceProfile


class AdaptiveDispatcher:
    """Select dispatch mode and apply bumpless output transitions."""

    def __init__(self, backend: MatlabDispatchBackend, ramp_rate_mw_per_s: float = 2.5) -> None:
        self.backend = backend
        self.ramp_rate_mw_per_s = ramp_rate_mw_per_s
        self.previous_command = [0.0, 0.0, 0.0, 0.0, 0.0]
        self.installed_pmax = [50.0, 40.0, 60.0, 55.0, 30.0]
        self.installed_pmin = [0.0, 0.0, 0.0, 0.0, -30.0]

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
        if mode == OperatingMode.GLOBAL:
            target, backend, note = self._global_dispatch(quality, resource, renewable_pmax)
        elif mode == OperatingMode.CLUSTER:
            target, backend, note = self._cluster_dispatch(clusters, resource)
        else:
            target, backend, note = self._autonomous_dispatch(resource)

        command = self._smooth(previous, target, interval_s)
        self.previous_command = command
        max_delta = max(abs(a - b) for a, b in zip(command, previous))
        return DispatchResult(mode, target, command, previous, max_delta, clusters, backend, note)

    def _global_dispatch(
        self,
        quality: QualitySnapshot,
        resource: ResourceSnapshot,
        renewable_pmax: Sequence[float] | None,
    ) -> tuple[List[float], str, str]:
        delay_steps = max(0, min(5, int(round(quality.average_delay_ms / 100.0))))
        p_max = list(renewable_pmax) if renewable_pmax is not None else ResourceProfile.availability_vector(resource)
        target, backend = self.backend.dispatch(resource.load_mw, delay_steps, quality.max_loss_rate, p_max=p_max)
        return (
            target,
            backend,
            f"global demand={resource.load_mw:.2f}MW delay_steps={delay_steps} dispatch_basis=forecast",
        )

    def _cluster_dispatch(self, clusters: List[List[int]], resource: ResourceSnapshot) -> tuple[List[float], str, str]:
        target = [0.0] * 5
        capacities = self.installed_pmax
        total_capacity = max(sum(capacities[node - 1] for group in clusters for node in group), 1e-9)

        for group in clusters:
            group_capacity = sum(capacities[node - 1] for node in group)
            group_demand = resource.load_mw * group_capacity / total_capacity
            equal_share = group_demand / len(group)
            for node in group:
                idx = node - 1
                target[idx] = min(max(equal_share, self.installed_pmin[idx]), self.installed_pmax[idx])
            self._rebalance_group(target, group, group_demand)

        return target, "local proportional cluster dispatch", f"clusters={clusters} dispatch_basis=forecast"

    def _autonomous_dispatch(self, resource: ResourceSnapshot) -> tuple[List[float], str, str]:
        availability = ResourceProfile.availability_vector(resource)
        bess_previous = self.previous_command[4]
        bess_safe = max(min(bess_previous * 0.90, 5.0), -5.0)
        target = [availability[0], availability[1], availability[2], availability[3], bess_safe]
        return (
            target,
            "autonomous fallback policy",
            "renewables follow forecast resource, BESS drifts toward safe band",
        )

    def _smooth(self, previous: Sequence[float], target: Sequence[float], interval_s: float) -> List[float]:
        max_step = self.ramp_rate_mw_per_s * max(interval_s, 1e-6)
        smoothed: List[float] = []
        for old, new in zip(previous, target):
            delta = min(max(new - old, -max_step), max_step)
            smoothed.append(old + delta)
        return smoothed

    def _rebalance_group(self, target: List[float], group: List[int], group_demand: float) -> None:
        for _ in range(40):
            current = sum(target[node - 1] for node in group)
            mismatch = group_demand - current
            if abs(mismatch) < 1e-8:
                return
            if mismatch > 0:
                free = [node for node in group if target[node - 1] < self.installed_pmax[node - 1] - 1e-9]
                if not free:
                    return
                step = mismatch / len(free)
                for node in free:
                    idx = node - 1
                    target[idx] = min(self.installed_pmax[idx], target[idx] + step)
            else:
                free = [node for node in group if target[node - 1] > self.installed_pmin[node - 1] + 1e-9]
                if not free:
                    return
                step = -mismatch / len(free)
                for node in free:
                    idx = node - 1
                    target[idx] = max(self.installed_pmin[idx], target[idx] - step)
