from __future__ import annotations

from .models import OperatingMode, StateDecision


class AdaptiveStateMachine:
    """Three-state decision logic with hysteresis and minimum dwell time."""

    def __init__(self, min_dwell_s: float = 3.0) -> None:
        self.min_dwell_s = min_dwell_s
        self.mode = OperatingMode.GLOBAL
        self.last_switch_s = 0.0

        self.global_to_cluster_delay_ms = 120.0
        self.global_to_cluster_loss = 0.15
        self.cluster_to_auto_delay_ms = 340.0
        self.cluster_to_auto_loss = 0.48

        self.auto_to_cluster_delay_ms = 260.0
        self.auto_to_cluster_loss = 0.35
        self.cluster_to_global_delay_ms = 90.0
        self.cluster_to_global_loss = 0.08

    def update(self, elapsed_s: float, average_delay_ms: float, max_loss_rate: float) -> StateDecision:
        previous = self.mode
        dwell = elapsed_s - self.last_switch_s
        next_mode = self.mode
        reason = "hold"

        if dwell < self.min_dwell_s:
            return StateDecision(previous, self.mode, False, "min_dwell_hold", dwell)

        if self.mode == OperatingMode.GLOBAL:
            if average_delay_ms >= self.global_to_cluster_delay_ms or max_loss_rate >= self.global_to_cluster_loss:
                next_mode = OperatingMode.CLUSTER
                reason = "degraded_to_cluster"
        elif self.mode == OperatingMode.CLUSTER:
            if average_delay_ms >= self.cluster_to_auto_delay_ms or max_loss_rate >= self.cluster_to_auto_loss:
                next_mode = OperatingMode.AUTONOMOUS
                reason = "severe_to_autonomous"
            elif average_delay_ms <= self.cluster_to_global_delay_ms and max_loss_rate <= self.cluster_to_global_loss:
                next_mode = OperatingMode.GLOBAL
                reason = "recovered_to_global"
        else:
            if average_delay_ms <= self.auto_to_cluster_delay_ms and max_loss_rate <= self.auto_to_cluster_loss:
                next_mode = OperatingMode.CLUSTER
                reason = "partial_recovery_to_cluster"

        changed = next_mode != self.mode
        if changed:
            self.mode = next_mode
            self.last_switch_s = elapsed_s

        return StateDecision(previous, self.mode, changed, reason, dwell)
