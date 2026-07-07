from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .models import DispatchResult, MODE_LABELS, QualitySnapshot, StateDecision


class RunLogger:
    """Write human-readable and JSONL logs for the adaptive demo."""

    def __init__(self, project_root: Path) -> None:
        log_dir = project_root / "logs" / "adaptive_vpp"
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.text_path = log_dir / f"adaptive_vpp_{stamp}.log"
        self.jsonl_path = log_dir / f"adaptive_vpp_{stamp}.jsonl"

        self.logger = logging.getLogger(f"adaptive_vpp_{stamp}")
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        handler = logging.FileHandler(self.text_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        self.logger.addHandler(handler)

    def info(self, message: str) -> None:
        self.logger.info(message)

    def backend_status(self, backend_label: str) -> None:
        self.info(f"MATLAB_ENGINE_STATUS backend={backend_label}")

    def transition(self, decision: StateDecision, quality: QualitySnapshot, dispatch: DispatchResult) -> None:
        self.info(
            "TRANSITION "
            f"t={quality.elapsed_s:.1f}s "
            f"{decision.previous_mode.name}->{decision.mode.name} "
            f"avg_delay={quality.average_delay_ms:.1f}ms "
            f"max_loss={quality.max_loss_rate:.3f} "
            f"reason={decision.reason} "
            f"clusters={dispatch.clusters} "
            f"max_output_delta={dispatch.max_delta_mw:.3f}MW "
            f"before={self._round_list(dispatch.previous_command_mw)} "
            f"after={self._round_list(dispatch.command_mw)}"
        )

    def snapshot(self, quality: QualitySnapshot, decision: StateDecision, dispatch: DispatchResult) -> None:
        payload: Dict[str, Any] = {
            "elapsed_s": round(quality.elapsed_s, 3),
            "mode": decision.mode.value,
            "mode_label": MODE_LABELS[decision.mode],
            "average_delay_ms": round(quality.average_delay_ms, 3),
            "max_loss_rate": round(quality.max_loss_rate, 5),
            "real_network_measurement": quality.real_network_measurement,
            "links": quality.compact_links(),
            "clusters": dispatch.clusters,
            "target_mw": self._round_list(dispatch.target_mw),
            "command_mw": self._round_list(dispatch.command_mw),
            "max_delta_mw": round(dispatch.max_delta_mw, 5),
            "backend": dispatch.backend,
            "note": dispatch.note,
        }
        with self.jsonl_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def print_key_fragments(self) -> None:
        print(f"\nLog file: {self.text_path}")
        print(f"JSONL telemetry: {self.jsonl_path}")
        print("\n=== Key log fragments ===")
        lines = self.text_path.read_text(encoding="utf-8").splitlines()
        selected = [line for line in lines if "TRANSITION" in line or "MATLAB_ENGINE_STATUS" in line]
        for line in selected:
            print(line)

    @staticmethod
    def _round_list(values: Iterable[float]) -> List[float]:
        return [round(float(value), 3) for value in values]
