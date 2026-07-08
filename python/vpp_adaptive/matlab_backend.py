from __future__ import annotations

from pathlib import Path
from typing import List, Sequence, Tuple


class MatlabDispatchBackend:
    """MATLAB Engine wrapper with a safe local fallback."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.available = False
        self.degraded_reason = ""
        self._engine = None
        self._cfg = None
        self.cost_a = [0.018, 0.023, 0.014, 0.017, 0.050]
        self.cost_b = [1.450, 1.550, 1.150, 1.250, 2.000]
        self.p_min = [0.0, 0.0, 0.0, 0.0, -30.0]
        self.p_max = [50.0, 40.0, 60.0, 55.0, 30.0]
        self._connect()

    @property
    def label(self) -> str:
        if self.available:
            return "MATLAB Engine et_admm_robust"
        return f"local fallback ({self.degraded_reason})"

    def dispatch(
        self,
        demand_mw: float,
        delay_steps: int,
        loss_rate: float,
        p_max: Sequence[float] | None = None,
    ) -> Tuple[List[float], str]:
        dynamic_p_max = list(p_max) if p_max is not None else self.p_max
        if self.available:
            try:
                p_opt, *_ = self._engine.et_admm_robust(
                    float(demand_mw),
                    self._cfg,
                    float(delay_steps),
                    float(loss_rate),
                    float("inf"),
                    float("inf"),
                    nargout=6,
                )
                target = min(max(float(demand_mw), sum(self.p_min)), sum(dynamic_p_max))
                return self._rebalance(
                    [float(row[0]) for row in p_opt],
                    target,
                    self.p_min,
                    dynamic_p_max,
                ), self.label
            except Exception as exc:  # pragma: no cover - depends on local MATLAB engine.
                self.available = False
                self.degraded_reason = f"MATLAB call failed: {exc}"

        return self.local_economic_dispatch(demand_mw, dynamic_p_max), self.label

    def local_economic_dispatch(self, demand_mw: float, p_max: Sequence[float] | None = None) -> List[float]:
        p_min = self.p_min
        p_max = list(p_max) if p_max is not None else self.p_max
        target = min(max(float(demand_mw), sum(p_min)), sum(p_max))

        lam_low = min(2 * a * p + b for a, b, p in zip(self.cost_a, self.cost_b, p_min)) - 100.0
        lam_high = max(2 * a * p + b for a, b, p in zip(self.cost_a, self.cost_b, p_max)) + 100.0
        dispatch = [0.0] * 5

        for _ in range(100):
            lam = 0.5 * (lam_low + lam_high)
            dispatch = [
                min(max((lam - b) / (2 * a), pmin), pmax)
                for a, b, pmin, pmax in zip(self.cost_a, self.cost_b, p_min, p_max)
            ]
            if sum(dispatch) < target:
                lam_low = lam
            else:
                lam_high = lam

        return self._rebalance(dispatch, target, p_min, p_max)

    def _connect(self) -> None:
        try:
            import matlab.engine  # type: ignore
        except Exception as exc:
            self.degraded_reason = f"MATLAB Engine unavailable: {exc}"
            return

        try:
            self._engine = matlab.engine.start_matlab()
            matlab_dir = str(self.project_root / "matlab")
            self._engine.addpath(self._engine.genpath(matlab_dir), nargout=0)
            self._cfg = self._engine.vpp_config(nargout=1)
            self.available = True
        except Exception as exc:  # pragma: no cover - depends on local MATLAB engine.
            self.available = False
            self.degraded_reason = f"MATLAB Engine connection failed: {exc}"

    @staticmethod
    def _rebalance(dispatch: Sequence[float], target: float, p_min: Sequence[float], p_max: Sequence[float]) -> List[float]:
        values = [min(max(float(x), lo), hi) for x, lo, hi in zip(dispatch, p_min, p_max)]
        for _ in range(80):
            mismatch = target - sum(values)
            if abs(mismatch) < 1e-9:
                break
            if mismatch > 0:
                free = [i for i, value in enumerate(values) if value < p_max[i] - 1e-9]
                if not free:
                    break
                step = mismatch / len(free)
                for i in free:
                    values[i] = min(p_max[i], values[i] + step)
            else:
                free = [i for i, value in enumerate(values) if value > p_min[i] + 1e-9]
                if not free:
                    break
                step = -mismatch / len(free)
                for i in free:
                    values[i] = max(p_min[i], values[i] - step)
        return values
