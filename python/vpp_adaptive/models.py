from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Tuple


class OperatingMode(str, Enum):
    GLOBAL = "global_cooperative"
    CLUSTER = "local_cluster"
    AUTONOMOUS = "autonomous"


MODE_LABELS = {
    OperatingMode.GLOBAL: "Global cooperative",
    OperatingMode.CLUSTER: "Local cluster",
    OperatingMode.AUTONOMOUS: "Autonomous",
}


@dataclass(frozen=True)
class LinkMetric:
    src: int
    dst: int
    delay_ms: float
    loss_rate: float
    available: bool
    configured_delay_ms: float | None = None
    configured_loss_rate: float | None = None
    measured_rtt_ms: float | None = None

    @property
    def key(self) -> str:
        return f"{self.src}-{self.dst}"


@dataclass(frozen=True)
class QualitySnapshot:
    elapsed_s: float
    links: Dict[str, LinkMetric]
    average_delay_ms: float
    max_loss_rate: float
    real_network_measurement: bool = False

    def compact_links(self) -> Dict[str, dict]:
        return {
            key: {
                "delay_ms": round(metric.delay_ms, 3),
                "loss_rate": round(metric.loss_rate, 5),
                "available": metric.available,
                "configured_delay_ms": (
                    round(metric.configured_delay_ms, 3)
                    if metric.configured_delay_ms is not None
                    else None
                ),
                "configured_loss_rate": (
                    round(metric.configured_loss_rate, 5)
                    if metric.configured_loss_rate is not None
                    else None
                ),
                "measured_rtt_ms": (
                    round(metric.measured_rtt_ms, 3)
                    if metric.measured_rtt_ms is not None
                    else None
                ),
            }
            for key, metric in self.links.items()
        }


@dataclass(frozen=True)
class StateDecision:
    previous_mode: OperatingMode
    mode: OperatingMode
    changed: bool
    reason: str
    dwell_s: float


@dataclass(frozen=True)
class ResourceSnapshot:
    hour_index: int
    solar_mw: Tuple[float, float]
    wind_mw: Tuple[float, float]
    load_mw: float


@dataclass(frozen=True)
class DispatchResult:
    mode: OperatingMode
    target_mw: List[float]
    command_mw: List[float]
    previous_command_mw: List[float]
    max_delta_mw: float
    clusters: List[List[int]]
    backend: str
    note: str
