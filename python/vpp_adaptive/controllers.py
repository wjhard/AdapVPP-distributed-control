from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence

from .matlab_backend import MatlabDispatchBackend
from .models import (
    ControllerTraceEntry,
    NodeDispatchSource,
    OperatingMode,
    QualitySnapshot,
    ResourceSnapshot,
)
from .resource_profile import ResourceProfile


@dataclass(frozen=True)
class ControllerContext:
    mode: OperatingMode
    quality: QualitySnapshot
    clusters: List[List[int]]
    resource: ResourceSnapshot
    previous_command: List[float]
    renewable_pmax: Sequence[float] | None
    installed_pmin: Sequence[float]
    installed_pmax: Sequence[float]
    backend: MatlabDispatchBackend

    @property
    def renewable_limit_mw(self) -> List[float]:
        if self.renewable_pmax is not None:
            return [float(value) for value in self.renewable_pmax[:4]]
        return [float(value) for value in ResourceProfile.availability_vector(self.resource)[:4]]

    @property
    def renewable_surplus_mw(self) -> float:
        return sum(self.renewable_limit_mw) - float(self.resource.load_mw)


@dataclass(frozen=True)
class ControllerUpdate:
    controller: str
    controller_key: str
    priority: int
    updates: Dict[int, float]
    reason: str
    node_reasons: Dict[int, str]
    backend: str | None = None

    @property
    def active(self) -> bool:
        return bool(self.updates)


@dataclass(frozen=True)
class ControllerRunResult:
    target_mw: List[float]
    backend: str
    note: str
    active_controllers: List[str]
    controller_trace: List[ControllerTraceEntry]
    dispatch_sources: List[NodeDispatchSource]


class DispatchController:
    name = "Base controller"
    key = "base"
    priority = 0

    def supports(self, mode: OperatingMode) -> bool:
        return True

    def run(self, context: ControllerContext, current_target: Sequence[float]) -> ControllerUpdate:
        raise NotImplementedError


class EconomicDispatchController(DispatchController):
    name = "经济调度控制器"
    key = "economic_dispatch"
    priority = 10

    def supports(self, mode: OperatingMode) -> bool:
        return mode == OperatingMode.GLOBAL

    def run(self, context: ControllerContext, current_target: Sequence[float]) -> ControllerUpdate:
        delay_steps = max(0, min(5, int(round(context.quality.average_delay_ms / 100.0))))
        p_max = (
            list(context.renewable_pmax)
            if context.renewable_pmax is not None
            else list(ResourceProfile.availability_vector(context.resource))
        )
        target, backend = context.backend.dispatch(
            context.resource.load_mw,
            delay_steps,
            context.quality.max_loss_rate,
            p_max=p_max,
        )
        reason = (
            f"全局协同经济调度: demand={context.resource.load_mw:.2f}MW, "
            f"delay_steps={delay_steps}, dispatch_basis=forecast"
        )
        return ControllerUpdate(
            controller=self.name,
            controller_key=self.key,
            priority=self.priority,
            updates={idx + 1: float(value) for idx, value in enumerate(target)},
            reason=reason,
            node_reasons={idx + 1: reason for idx in range(5)},
            backend=backend,
        )


class LocalClusterCoordinationController(DispatchController):
    name = "局部聚类协调控制器"
    key = "local_cluster_coordination"
    priority = 10

    def supports(self, mode: OperatingMode) -> bool:
        return mode == OperatingMode.CLUSTER

    def run(self, context: ControllerContext, current_target: Sequence[float]) -> ControllerUpdate:
        target = [0.0] * 5
        total_capacity = max(
            sum(context.installed_pmax[node - 1] for group in context.clusters for node in group),
            1e-9,
        )

        for group in context.clusters:
            group_capacity = sum(context.installed_pmax[node - 1] for node in group)
            group_demand = context.resource.load_mw * group_capacity / total_capacity
            equal_share = group_demand / len(group)
            for node in group:
                idx = node - 1
                target[idx] = min(
                    max(equal_share, context.installed_pmin[idx]),
                    context.installed_pmax[idx],
                )
            rebalance_group(target, group, group_demand, context.installed_pmin, context.installed_pmax)

        reason = f"按连通分量局部协调: clusters={context.clusters}, dispatch_basis=forecast"
        return ControllerUpdate(
            controller=self.name,
            controller_key=self.key,
            priority=self.priority,
            updates={idx + 1: float(value) for idx, value in enumerate(target)},
            reason=reason,
            node_reasons={idx + 1: reason for idx in range(5)},
            backend="local proportional cluster dispatch",
        )


class EmergencyConservativeController(DispatchController):
    name = "应急保守控制器"
    key = "emergency_conservative"
    priority = 10

    def supports(self, mode: OperatingMode) -> bool:
        return mode == OperatingMode.AUTONOMOUS

    def run(self, context: ControllerContext, current_target: Sequence[float]) -> ControllerUpdate:
        availability = ResourceProfile.availability_vector(context.resource)
        bess_previous = context.previous_command[4]
        bess_safe = max(min(bess_previous * 0.90, 5.0), -5.0)
        target = [availability[0], availability[1], availability[2], availability[3], bess_safe]
        reason = "完全自治兜底: 可再生按预测资源跟随, BESS缓慢回到安全功率带"
        return ControllerUpdate(
            controller=self.name,
            controller_key=self.key,
            priority=self.priority,
            updates={idx + 1: float(value) for idx, value in enumerate(target)},
            reason=reason,
            node_reasons={idx + 1: reason for idx in range(5)},
            backend="autonomous fallback policy",
        )


class StoragePriorityChargeController(DispatchController):
    name = "储能优先充电控制器"
    key = "storage_priority_charge"
    priority = 90

    def __init__(
        self,
        target_soc: float = 0.65,
        initial_soc: float = 0.42,
        surplus_threshold_mw: float = 5.0,
        force_test: bool = False,
    ) -> None:
        self.target_soc = target_soc
        self.soc = initial_soc
        self.surplus_threshold_mw = surplus_threshold_mw
        self.force_test = force_test
        self.capacity_mwh = 60.0

    def supports(self, mode: OperatingMode) -> bool:
        return True

    def run(self, context: ControllerContext, current_target: Sequence[float]) -> ControllerUpdate:
        surplus = context.renewable_surplus_mw
        should_charge = (
            self.force_test
            or (surplus >= self.surplus_threshold_mw and self.soc < self.target_soc)
        )
        if not should_charge:
            return ControllerUpdate(
                controller=self.name,
                controller_key=self.key,
                priority=self.priority,
                updates={},
                reason=(
                    f"未触发: surplus={surplus:.2f}MW, "
                    f"soc={self.soc:.1%}, target={self.target_soc:.1%}"
                ),
                node_reasons={},
            )

        current_bess_mw = float(current_target[4])
        renewable_limits = context.renewable_limit_mw
        headroom = [
            max(0.0, float(limit) - float(current_target[idx]))
            for idx, limit in enumerate(renewable_limits)
        ]
        available_headroom = sum(headroom)
        max_extra_charge = min(
            current_bess_mw - context.installed_pmin[4],
            available_headroom,
            surplus if surplus > 0.0 else (available_headroom if self.force_test else 0.0),
        )
        if max_extra_charge <= 1e-6:
            return ControllerUpdate(
                controller=self.name,
                controller_key=self.key,
                priority=self.priority,
                updates={},
                reason=(
                    f"无法增加充电: current={current_bess_mw:.2f}MW, "
                    f"surplus={surplus:.2f}MW, renewable_headroom={available_headroom:.2f}MW"
                ),
                node_reasons={},
            )

        desired_bess_mw = current_bess_mw - max_extra_charge
        if self.force_test and surplus < self.surplus_threshold_mw:
            reason = (
                f"测试强制触发: surplus={surplus:.2f}MW, SOC={self.soc:.1%}<"
                f"{self.target_soc:.1%}, 覆盖BESS并补足可再生出力验证优先级机制"
            )
        else:
            reason = (
                f"可再生预测出力富余{surplus:.2f}MW且SOC={self.soc:.1%}<"
                f"{self.target_soc:.1%}, 覆盖BESS指令为优先充电并释放可再生出力"
            )

        updates: Dict[int, float] = {5: desired_bess_mw}
        node_reasons: Dict[int, str] = {5: reason}
        remaining = max_extra_charge
        for idx, room in enumerate(headroom):
            if remaining <= 1e-9 or room <= 1e-9:
                continue
            extra = min(room, remaining)
            updates[idx + 1] = float(current_target[idx]) + extra
            node_reasons[idx + 1] = (
                f"为BESS新增充电{max_extra_charge:.2f}MW释放预测可再生出力"
            )
            remaining -= extra

        return ControllerUpdate(
            controller=self.name,
            controller_key=self.key,
            priority=self.priority,
            updates=updates,
            reason=reason,
            node_reasons=node_reasons,
            backend=None,
        )

    def observe_command(self, bess_command_mw: float, interval_s: float) -> None:
        energy_mwh = abs(float(bess_command_mw)) * max(interval_s, 0.0) / 3600.0
        if bess_command_mw < 0.0:
            self.soc = min(1.0, self.soc + energy_mwh * 0.95 / self.capacity_mwh)
        elif bess_command_mw > 0.0:
            self.soc = max(0.0, self.soc - energy_mwh / (0.95 * self.capacity_mwh))


class ControllerManager:
    """Run named controllers in priority order and keep node-level provenance."""

    def __init__(self, backend: MatlabDispatchBackend, force_storage_charge_test: bool = False) -> None:
        self.backend = backend
        self.storage_controller = StoragePriorityChargeController(force_test=force_storage_charge_test)
        self.controllers: List[DispatchController] = [
            EconomicDispatchController(),
            LocalClusterCoordinationController(),
            EmergencyConservativeController(),
            self.storage_controller,
        ]

    def run(
        self,
        mode: OperatingMode,
        quality: QualitySnapshot,
        clusters: List[List[int]],
        resource: ResourceSnapshot,
        previous_command: Sequence[float],
        installed_pmin: Sequence[float],
        installed_pmax: Sequence[float],
        renewable_pmax: Sequence[float] | None = None,
    ) -> ControllerRunResult:
        context = ControllerContext(
            mode=mode,
            quality=quality,
            clusters=clusters,
            resource=resource,
            previous_command=list(previous_command),
            renewable_pmax=renewable_pmax,
            installed_pmin=installed_pmin,
            installed_pmax=installed_pmax,
            backend=self.backend,
        )
        target = list(previous_command)
        active_controllers: List[str] = []
        trace: List[ControllerTraceEntry] = []
        sources: Dict[int, NodeDispatchSource] = {}
        backend_label = "controller manager"
        notes: List[str] = []

        for controller in sorted(self.controllers, key=lambda item: item.priority):
            if not controller.supports(mode):
                continue
            update = controller.run(context, target)
            if not update.active:
                continue

            active_controllers.append(update.controller)
            nodes = sorted(update.updates)
            trace.append(
                ControllerTraceEntry(
                    controller=update.controller,
                    controller_key=update.controller_key,
                    priority=update.priority,
                    action="override" if any(node in sources for node in nodes) else "set",
                    reason=update.reason,
                    nodes=nodes,
                )
            )
            notes.append(f"{update.controller}: {update.reason}")
            if update.backend:
                backend_label = update.backend

            for node, value in update.updates.items():
                idx = node - 1
                previous_source = sources.get(node)
                previous_value = target[idx]
                is_override = previous_source is not None and abs(float(value) - previous_value) > 1e-9
                node_reason = update.node_reasons.get(node, update.reason)
                sources[node] = NodeDispatchSource(
                    node=node,
                    controller=update.controller,
                    controller_key=update.controller_key,
                    priority=update.priority,
                    reason=node_reason,
                    overridden=is_override,
                    previous_controller=previous_source.controller if previous_source else None,
                    previous_value_mw=previous_value if previous_source else None,
                    override_reason=node_reason if is_override else None,
                )
                target[idx] = float(value)

        for node in range(1, 6):
            if node not in sources:
                sources[node] = NodeDispatchSource(
                    node=node,
                    controller="未分配控制器",
                    controller_key="unassigned",
                    priority=-1,
                    reason="没有控制器写入该节点，保持上一时刻指令",
                )

        return ControllerRunResult(
            target_mw=target,
            backend=backend_label,
            note=" | ".join(notes),
            active_controllers=active_controllers,
            controller_trace=trace,
            dispatch_sources=[sources[node] for node in range(1, 6)],
        )

    def observe_command(self, command_mw: Sequence[float], interval_s: float) -> None:
        self.storage_controller.observe_command(command_mw[4], interval_s)


def rebalance_group(
    target: List[float],
    group: List[int],
    group_demand: float,
    p_min: Sequence[float],
    p_max: Sequence[float],
) -> None:
    for _ in range(40):
        current = sum(target[node - 1] for node in group)
        mismatch = group_demand - current
        if abs(mismatch) < 1e-8:
            return
        if mismatch > 0:
            free = [node for node in group if target[node - 1] < p_max[node - 1] - 1e-9]
            if not free:
                return
            step = mismatch / len(free)
            for node in free:
                idx = node - 1
                target[idx] = min(p_max[idx], target[idx] + step)
        else:
            free = [node for node in group if target[node - 1] > p_min[node - 1] + 1e-9]
            if not free:
                return
            step = -mismatch / len(free)
            for node in free:
                idx = node - 1
                target[idx] = max(p_min[idx], target[idx] - step)
