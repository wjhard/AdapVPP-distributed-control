from __future__ import annotations

import math
import random
from itertools import combinations
from typing import Dict, Iterable, Tuple

from .models import LinkMetric, QualitySnapshot


class LinkQualitySimulator:
    """Generate a full fault-recovery communication quality cycle."""

    def __init__(
        self,
        node_ids: Iterable[int] = range(1, 6),
        cycle_s: float = 120.0,
        seed: int = 20260702,
        availability_loss_threshold: float = 0.35,
        availability_delay_threshold_ms: float = 320.0,
    ) -> None:
        self.node_ids = list(node_ids)
        self.cycle_s = cycle_s
        self.seed = seed
        self.availability_loss_threshold = availability_loss_threshold
        self.availability_delay_threshold_ms = availability_delay_threshold_ms
        self.links = list(combinations(self.node_ids, 2))
        rng = random.Random(seed)
        self._bias: Dict[Tuple[int, int], Tuple[float, float, float]] = {
            link: (rng.uniform(-0.12, 0.12), rng.uniform(0.0, math.tau), rng.uniform(0.85, 1.15))
            for link in self.links
        }
        self._outage_links = {(1, 4), (2, 3), (3, 5), (4, 5)}

    def sample(self, elapsed_s: float) -> QualitySnapshot:
        t = elapsed_s % self.cycle_s
        severity = self._severity(t)
        outage_weight = self._outage_weight(t)
        metrics: Dict[str, LinkMetric] = {}

        for idx, link in enumerate(self.links):
            delay_ms, loss_rate = self._link_values(link, idx, t, severity, outage_weight)
            available = (
                loss_rate < self.availability_loss_threshold
                and delay_ms < self.availability_delay_threshold_ms
            )
            metric = LinkMetric(link[0], link[1], delay_ms, loss_rate, available)
            metrics[metric.key] = metric

        average_delay = sum(item.delay_ms for item in metrics.values()) / len(metrics)
        max_loss = max(item.loss_rate for item in metrics.values())
        return QualitySnapshot(elapsed_s, metrics, average_delay, max_loss)

    def _severity(self, t: float) -> float:
        if t < 20:
            return 0.0
        if t < 40:
            return self._lerp(0.0, 0.45, (t - 20) / 20)
        if t < 60:
            return self._lerp(0.45, 0.85, (t - 40) / 20)
        if t < 78:
            return 0.92
        if t < 100:
            return self._lerp(0.80, 0.25, (t - 78) / 22)
        if t < 115:
            return self._lerp(0.25, 0.0, (t - 100) / 15)
        return 0.0

    def _outage_weight(self, t: float) -> float:
        if t < 60 or t > 84:
            return 0.0
        if t < 66:
            return (t - 60) / 6
        if t < 78:
            return 1.0
        return max(0.0, 1 - (t - 78) / 6)

    def _link_values(
        self,
        link: Tuple[int, int],
        idx: int,
        t: float,
        severity: float,
        outage_weight: float,
    ) -> Tuple[float, float]:
        bias, phase, scale = self._bias[link]
        wave = math.sin(t / (4.8 + idx * 0.17) + phase)
        fast_wave = math.sin(t / (1.9 + idx * 0.11) + phase * 0.7)

        delay_ms = 42 + 430 * severity * scale + 10 * wave + 6 * fast_wave + 25 * bias
        loss_rate = 0.012 + 0.55 * severity * (0.94 + 0.25 * bias) + 0.018 * wave + 0.008 * fast_wave

        if tuple(sorted(link)) in self._outage_links:
            delay_ms += outage_weight * (260 + 40 * idx)
            loss_rate += outage_weight * (0.35 + 0.05 * (idx % 3))
        else:
            delay_ms += outage_weight * 60
            loss_rate += outage_weight * 0.05

        delay_ms = max(20.0, delay_ms)
        loss_rate = min(max(loss_rate, 0.0), 1.0)
        return delay_ms, loss_rate

    @staticmethod
    def _lerp(start: float, end: float, ratio: float) -> float:
        ratio = min(max(ratio, 0.0), 1.0)
        return start + (end - start) * ratio
