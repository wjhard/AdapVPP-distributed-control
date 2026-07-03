from __future__ import annotations

import math
import random
from dataclasses import dataclass
from itertools import combinations
from statistics import mean
from typing import Dict, Iterable, List, Tuple

from .models import LinkMetric, QualitySnapshot


GOOD = "Good"
BAD = "Bad"
ChannelState = str


@dataclass(frozen=True)
class GilbertElliottLinkConfig:
    """Per-link parameters for a two-state Gilbert-Elliott channel."""

    fragility: float
    good_loss_base: float
    bad_loss_base: float
    good_delay_ms: float
    bad_delay_ms: float
    delay_jitter_ms: float


@dataclass(frozen=True)
class LinkStateRecord:
    elapsed_s: float
    state: ChannelState
    delay_ms: float
    loss_rate: float
    available: bool
    p_good_to_bad: float
    p_bad_to_good: float


class LinkQualitySimulator:
    """Generate link quality using Gilbert-Elliott two-state Markov channels.

    The Gilbert-Elliott model is a standard networked-control-system model for
    burst packet loss: every link switches between a Good state with low loss and
    a Bad state with high loss. The transition probabilities are slowly modulated
    over the 120 s demo to create the required fault-recovery envelope, while the
    actual Good/Bad residence times remain stochastic Markov-chain outcomes.
    """

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

        config_rng = random.Random(seed)
        self._remote_links = {(1, 4), (2, 3), (3, 5), (4, 5)}
        self._configs: Dict[Tuple[int, int], GilbertElliottLinkConfig] = {}
        self._rngs: Dict[Tuple[int, int], random.Random] = {}
        self._states: Dict[Tuple[int, int], ChannelState] = {}
        self._history: Dict[Tuple[int, int], List[LinkStateRecord]] = {}
        self._last_elapsed_s: float | None = None

        for idx, link in enumerate(self.links):
            remote_factor = 1.28 if tuple(sorted(link)) in self._remote_links else 1.0
            span_factor = 1.0 + 0.05 * abs(link[0] - link[1])
            fragility = remote_factor * span_factor * config_rng.uniform(0.9, 1.12)
            self._configs[link] = GilbertElliottLinkConfig(
                fragility=fragility,
                good_loss_base=config_rng.uniform(0.010, 0.026),
                bad_loss_base=config_rng.uniform(0.64, 0.86),
                good_delay_ms=config_rng.uniform(36.0, 58.0) * span_factor,
                bad_delay_ms=config_rng.uniform(340.0, 520.0) * remote_factor,
                delay_jitter_ms=config_rng.uniform(4.0, 9.0),
            )
            self._rngs[link] = random.Random(seed + 9973 * (idx + 1))
            self._states[link] = GOOD
            self._history[link] = []

    def sample(self, elapsed_s: float) -> QualitySnapshot:
        if self._last_elapsed_s is not None and elapsed_s < self._last_elapsed_s:
            self.reset()

        t = min(max(elapsed_s, 0.0), self.cycle_s)
        dt = 0.0 if self._last_elapsed_s is None else max(0.0, elapsed_s - self._last_elapsed_s)
        metrics: Dict[str, LinkMetric] = {}

        for link in self.links:
            p_good_to_bad, p_bad_to_good = self._transition_probabilities(link, t)
            if dt > 0.0:
                self._advance_state(link, p_good_to_bad, p_bad_to_good, dt)

            delay_ms, loss_rate = self._sample_observation(link, t)
            available = (
                loss_rate < self.availability_loss_threshold
                and delay_ms < self.availability_delay_threshold_ms
            )
            metric = LinkMetric(link[0], link[1], delay_ms, loss_rate, available)
            metrics[metric.key] = metric
            self._history[link].append(
                LinkStateRecord(
                    elapsed_s=elapsed_s,
                    state=self._states[link],
                    delay_ms=delay_ms,
                    loss_rate=loss_rate,
                    available=available,
                    p_good_to_bad=p_good_to_bad,
                    p_bad_to_good=p_bad_to_good,
                )
            )

        self._last_elapsed_s = elapsed_s
        average_delay = sum(item.delay_ms for item in metrics.values()) / len(metrics)
        max_loss = max(item.loss_rate for item in metrics.values())
        return QualitySnapshot(elapsed_s, metrics, average_delay, max_loss)

    def reset(self) -> None:
        self._last_elapsed_s = None
        for link in self.links:
            self._states[link] = GOOD
            self._history[link] = []

    def bad_state_ratios(self) -> Dict[str, float]:
        ratios: Dict[str, float] = {}
        for link, records in self._history.items():
            if not records:
                ratios[self._key(link)] = 0.0
                continue
            bad_count = sum(1 for record in records if record.state == BAD)
            ratios[self._key(link)] = bad_count / len(records)
        return ratios

    def aggregate_statistics(self) -> Dict[str, float]:
        records = [record for link_records in self._history.values() for record in link_records]
        if not records:
            return {"average_link_delay_ms": 0.0, "average_link_loss_rate": 0.0}
        return {
            "average_link_delay_ms": mean(record.delay_ms for record in records),
            "average_link_loss_rate": mean(record.loss_rate for record in records),
            "bad_state_ratio": mean(1.0 if record.state == BAD else 0.0 for record in records),
        }

    def diagnostic_lines(self) -> List[str]:
        lines = [
            "LINK_MODEL Gilbert-Elliott two-state Markov channel "
            "(Good=low loss, Bad=burst weak communication)",
            "BAD_STATE_RATIO_BY_LINK",
        ]
        for key, ratio in self.bad_state_ratios().items():
            lines.append(f"  link {key}: {ratio * 100:.1f}%")

        stats = self.aggregate_statistics()
        lines.append(
            "AGGREGATE_LINK_STATS "
            f"avg_delay={stats['average_link_delay_ms']:.1f}ms "
            f"avg_loss={stats['average_link_loss_rate']:.3f} "
            f"bad_ratio={stats['bad_state_ratio'] * 100:.1f}%"
        )
        lines.extend(self._burst_sample_lines())
        return lines

    def _advance_state(
        self,
        link: Tuple[int, int],
        p_good_to_bad: float,
        p_bad_to_good: float,
        dt: float,
    ) -> None:
        rng = self._rngs[link]
        p_gb = self._scale_probability(p_good_to_bad, dt)
        p_bg = self._scale_probability(p_bad_to_good, dt)

        if self._states[link] == GOOD:
            if rng.random() < p_gb:
                self._states[link] = BAD
        elif rng.random() < p_bg:
            self._states[link] = GOOD

    def _transition_probabilities(self, link: Tuple[int, int], t: float) -> Tuple[float, float]:
        config = self._configs[link]
        envelope = self._event_envelope(t)
        recovery_suppression = 1.0 - 0.98 * self._sigmoid((t - 98.0) / 2.5)

        normal_good_to_bad = 0.00001 * config.fragility
        event_good_to_bad = 0.076 * config.fragility * envelope * recovery_suppression
        severe_good_to_bad = 0.058 * config.fragility * envelope**2 * recovery_suppression
        p_good_to_bad = min(0.28, normal_good_to_bad + event_good_to_bad + severe_good_to_bad)

        normal_bad_to_good = 0.72 / math.sqrt(config.fragility)
        event_bad_to_good = 0.042 / config.fragility
        p_bad_to_good = max(
            0.018,
            normal_bad_to_good * (1.0 - envelope) + event_bad_to_good * envelope,
        )
        recovery_boost = 0.98 * self._sigmoid((t - 89.0) / 2.4) * (1.0 - 0.35 * envelope)
        p_bad_to_good = max(p_bad_to_good, recovery_boost)
        return p_good_to_bad, p_bad_to_good

    def _sample_observation(self, link: Tuple[int, int], t: float) -> Tuple[float, float]:
        config = self._configs[link]
        rng = self._rngs[link]
        envelope = self._event_envelope(t)

        if self._states[link] == GOOD:
            delay_ms = (
                config.good_delay_ms
                + 22.0 * envelope * config.fragility
                + rng.gauss(0.0, config.delay_jitter_ms)
            )
            loss_rate = config.good_loss_base + 0.012 * envelope + abs(rng.gauss(0.0, 0.003))
        else:
            delay_ms = (
                config.bad_delay_ms
                + 88.0 * envelope
                + rng.gauss(0.0, config.delay_jitter_ms * 3.4)
            )
            loss_rate = config.bad_loss_base + 0.052 * envelope + rng.gauss(0.0, 0.032)

        return max(20.0, delay_ms), min(max(loss_rate, 0.0), 0.98)

    def _event_envelope(self, t: float) -> float:
        rise = self._sigmoid((t - 39.0) / 6.5)
        fall = self._sigmoid((86.0 - t) / 5.5)
        plateau = rise * fall
        severe_core = math.exp(-0.5 * ((t - 68.0) / 17.0) ** 2)
        return min(1.0, 0.82 * plateau + 0.18 * severe_core)

    def _burst_sample_lines(self, max_links: int = 4, window_size: int = 8) -> List[str]:
        lines = ["BURST_SAMPLE_WINDOWS"]
        ranked_links = sorted(
            self.links,
            key=lambda link: self.bad_state_ratios().get(self._key(link), 0.0),
            reverse=True,
        )
        for link in ranked_links[:max_links]:
            records = self._longest_bad_window(self._history[link], window_size)
            if not records:
                continue
            values = "; ".join(
                f"{record.elapsed_s:.0f}s {record.state[0]} "
                f"loss={record.loss_rate:.2f} delay={record.delay_ms:.0f}"
                for record in records
            )
            lines.append(f"  link {self._key(link)}: {values}")
        return lines

    @staticmethod
    def _longest_bad_window(records: List[LinkStateRecord], window_size: int) -> List[LinkStateRecord]:
        best_start = -1
        best_len = 0
        current_start = -1
        current_len = 0

        for idx, record in enumerate(records):
            if record.state == BAD:
                if current_len == 0:
                    current_start = idx
                current_len += 1
                if current_len > best_len:
                    best_start = current_start
                    best_len = current_len
            else:
                current_start = -1
                current_len = 0

        if best_start < 0:
            return records[:window_size]
        return records[best_start : best_start + min(window_size, best_len)]

    @staticmethod
    def _scale_probability(probability_per_second: float, dt: float) -> float:
        probability_per_second = min(max(probability_per_second, 0.0), 1.0)
        return 1.0 - (1.0 - probability_per_second) ** max(dt, 0.0)

    @staticmethod
    def _sigmoid(value: float) -> float:
        return 1.0 / (1.0 + math.exp(-value))

    @staticmethod
    def _key(link: Tuple[int, int]) -> str:
        return f"{link[0]}-{link[1]}"
