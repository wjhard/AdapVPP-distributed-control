from __future__ import annotations

from pathlib import Path
from typing import Tuple

import numpy as np
import scipy.io as sio

from .models import ResourceSnapshot


class ResourceProfile:
    """Load the existing MATLAB typical-day dataset for renewable/load signals."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        path = project_root / "data" / "processed" / "matlab" / "vpp_typical_day.mat"
        if path.exists():
            data = sio.loadmat(path)
            self.solar = np.asarray(data["P_solar"], dtype=float)
            self.wind = np.asarray(data["P_wind"], dtype=float)
            self.load = np.asarray(data["P_load"], dtype=float).reshape(-1)
        else:
            hours = np.arange(24)
            solar_shape = np.maximum(0.0, np.sin((hours - 6) / 12 * np.pi))
            self.solar = np.column_stack((50 * solar_shape, 40 * solar_shape))
            self.wind = np.column_stack((18 + 7 * np.sin(hours / 24 * 2 * np.pi), 16 + 6 * np.cos(hours / 24 * 2 * np.pi)))
            self.load = 55 + 20 * np.sin((hours - 8) / 24 * 2 * np.pi) ** 2

    def sample(self, elapsed_s: float, duration_s: float) -> ResourceSnapshot:
        idx = int((elapsed_s / max(duration_s, 1.0)) * len(self.load)) % len(self.load)
        return ResourceSnapshot(
            hour_index=idx + 1,
            solar_mw=(float(self.solar[idx, 0]), float(self.solar[idx, 1])),
            wind_mw=(float(self.wind[idx, 0]), float(self.wind[idx, 1])),
            load_mw=float(self.load[idx]),
        )

    @staticmethod
    def availability_vector(snapshot: ResourceSnapshot) -> Tuple[float, float, float, float, float]:
        return (
            snapshot.solar_mw[0],
            snapshot.solar_mw[1],
            snapshot.wind_mw[0],
            snapshot.wind_mw[1],
            30.0,
        )
