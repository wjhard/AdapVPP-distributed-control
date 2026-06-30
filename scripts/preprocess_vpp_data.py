from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from netCDF4 import Dataset
import numpy as np
import pandas as pd
import pvlib
import scipy.io as sio


PROJECT_ROOT = Path(__file__).resolve().parents[1]
os.chdir(PROJECT_ROOT)
ERA5_DIR = PROJECT_ROOT / "data" / "raw" / "era5"
LOAD_DIR = PROJECT_ROOT / "data" / "raw" / "load"
SOLAR_OUT_DIR = PROJECT_ROOT / "data" / "processed" / "solar"
WIND_OUT_DIR = PROJECT_ROOT / "data" / "processed" / "wind"
MATLAB_OUT_DIR = PROJECT_ROOT / "data" / "processed" / "matlab"


@dataclass(frozen=True)
class Node:
    node_id: int
    kind: str
    capacity_mw: float
    latitude: float | None = None
    longitude: float | None = None


SOLAR_NODES = [
    Node(1, "solar", 50.0, 26.6, 106.7),
    Node(2, "solar", 40.0, 27.3, 105.9),
]
WIND_NODES = [
    Node(3, "wind", 60.0, 28.1, 107.2),
    Node(4, "wind", 55.0, 25.8, 104.8),
]
ALL_NODES = [
    *SOLAR_NODES,
    *WIND_NODES,
    Node(5, "bess", 30.0),
    Node(6, "load", 80.0),
]


def log(message: str) -> None:
    print(message, flush=True)


def ensure_dirs() -> None:
    for path in (SOLAR_OUT_DIR, WIND_OUT_DIR, MATLAB_OUT_DIR):
        path.mkdir(parents=True, exist_ok=True)


def nc_local_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        return str(path)


class Era5Dataset:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.ds = Dataset(nc_local_path(path))
        self.time_name = "valid_time" if "valid_time" in self.ds.variables else "time"
        self.lat_name = "latitude" if "latitude" in self.ds.variables else "lat"
        self.lon_name = "longitude" if "longitude" in self.ds.variables else "lon"

    def __enter__(self) -> "Era5Dataset":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def close(self) -> None:
        self.ds.close()

    def get_var(self, candidates: tuple[str, ...]):
        for name in candidates:
            if name in self.ds.variables:
                return self.ds.variables[name]
        lower_map = {name.lower(): name for name in self.ds.variables}
        for name in candidates:
            if name.lower() in lower_map:
                return self.ds.variables[lower_map[name.lower()]]
        raise KeyError(f"missing variable, tried {candidates}; available={list(self.ds.variables)}")

    def point_series(self, candidates: tuple[str, ...], latitude: float, longitude: float) -> np.ndarray:
        var = self.get_var(candidates)
        lat_values = np.asarray(self.ds.variables[self.lat_name][:], dtype=float)
        lon_values = np.asarray(self.ds.variables[self.lon_name][:], dtype=float)
        lat_idx = int(np.nanargmin(np.abs(lat_values - latitude)))
        lon_idx = int(np.nanargmin(np.abs(lon_values - longitude)))
        selectors = []
        for dim in var.dimensions:
            if dim == self.time_name:
                selectors.append(slice(None))
            elif dim == self.lat_name:
                selectors.append(lat_idx)
            elif dim == self.lon_name:
                selectors.append(lon_idx)
            else:
                selectors.append(0)
        return np.asarray(var[tuple(selectors)], dtype=float).reshape(-1)

    def time_index(self) -> pd.DatetimeIndex:
        var = self.ds.variables[self.time_name]
        units = getattr(var, "units", "")
        values = np.asarray(var[:])
        if units.startswith("seconds since 1970-01-01"):
            return pd.to_datetime(values[:8760], unit="s", utc=True)
        return pd.to_datetime(values[:8760], utc=True)


def normalized_length(values: np.ndarray, n: int = 8760) -> np.ndarray:
    values = np.asarray(values, dtype=float).reshape(-1)
    if len(values) < n:
        raise ValueError(f"series has {len(values)} samples, expected at least {n}")
    return values[:n]


def wind_power_curve(speed_mps: np.ndarray, capacity_mw: float) -> np.ndarray:
    cut_in = 3.0
    rated = 12.0
    cut_out = 25.0
    speed = np.asarray(speed_mps, dtype=float)
    pu = np.zeros_like(speed)
    ramp = (speed >= cut_in) & (speed < rated)
    pu[ramp] = (speed[ramp] ** 3 - cut_in**3) / (rated**3 - cut_in**3)
    pu[(speed >= rated) & (speed <= cut_out)] = 1.0
    return np.clip(pu * capacity_mw, 0.0, capacity_mw)


def as_float_array(values) -> np.ndarray:
    if hasattr(values, "to_numpy"):
        return np.asarray(values.to_numpy(), dtype=float)
    return np.asarray(values, dtype=float)


def preprocess_wind(wind_ds: Era5Dataset) -> pd.DataFrame:
    out: dict[str, np.ndarray] = {}
    for node in WIND_NODES:
        assert node.latitude is not None and node.longitude is not None
        u = normalized_length(wind_ds.point_series(("u10", "10m_u_component_of_wind"), node.latitude, node.longitude))
        v = normalized_length(wind_ds.point_series(("v10", "10m_v_component_of_wind"), node.latitude, node.longitude))
        speed10 = np.sqrt(u**2 + v**2)
        speed100 = speed10 * (100.0 / 10.0) ** 0.143
        out[f"node_{node.node_id}_wind_mw"] = wind_power_curve(speed100, node.capacity_mw)
        out[f"node_{node.node_id}_wind_speed_100m_mps"] = speed100
    df = pd.DataFrame(out)
    return df


def solar_power_pvlib(
    ghi_wm2: np.ndarray,
    temp_air_c: np.ndarray,
    wind_speed_mps: np.ndarray,
    times_utc: pd.DatetimeIndex,
    node: Node,
) -> np.ndarray:
    assert node.latitude is not None and node.longitude is not None
    times_local = times_utc.tz_convert("Asia/Shanghai")
    location = pvlib.location.Location(
        latitude=node.latitude,
        longitude=node.longitude,
        tz="Asia/Shanghai",
        altitude=1100,
    )
    solar_position = location.get_solarposition(times_local)
    erbs = pvlib.irradiance.erbs(
        ghi=np.clip(ghi_wm2, 0.0, None),
        zenith=solar_position["zenith"].to_numpy(),
        datetime_or_doy=times_local,
    )
    poa = pvlib.irradiance.get_total_irradiance(
        surface_tilt=25.0,
        surface_azimuth=180.0,
        solar_zenith=solar_position["zenith"].to_numpy(),
        solar_azimuth=solar_position["azimuth"].to_numpy(),
        dni=np.nan_to_num(as_float_array(erbs["dni"]), nan=0.0),
        ghi=np.clip(ghi_wm2, 0.0, None),
        dhi=np.nan_to_num(as_float_array(erbs["dhi"]), nan=0.0),
    )
    temp_params = pvlib.temperature.TEMPERATURE_MODEL_PARAMETERS["sapm"]["open_rack_glass_glass"]
    temp_cell = pvlib.temperature.sapm_cell(
        as_float_array(poa["poa_global"]),
        temp_air_c,
        wind_speed_mps,
        **temp_params,
    )
    power = pvlib.pvsystem.pvwatts_dc(
        effective_irradiance=np.nan_to_num(as_float_array(poa["poa_global"]), nan=0.0),
        temp_cell=temp_cell,
        pdc0=node.capacity_mw,
        gamma_pdc=-0.004,
    )
    return np.clip(np.nan_to_num(power, nan=0.0), 0.0, node.capacity_mw)


def preprocess_solar(solar_ds: Era5Dataset, wind_ds: Era5Dataset, times_utc: pd.DatetimeIndex) -> pd.DataFrame:
    out: dict[str, np.ndarray] = {}
    for node in SOLAR_NODES:
        assert node.latitude is not None and node.longitude is not None
        ssrd_node = normalized_length(
            solar_ds.point_series(("ssrd", "surface_solar_radiation_downwards"), node.latitude, node.longitude)
        )
        temp_k = normalized_length(solar_ds.point_series(("t2m", "2m_temperature"), node.latitude, node.longitude))
        u = normalized_length(wind_ds.point_series(("u10", "10m_u_component_of_wind"), node.latitude, node.longitude))
        v = normalized_length(wind_ds.point_series(("v10", "10m_v_component_of_wind"), node.latitude, node.longitude))
        ghi = np.clip(ssrd_node / 3600.0, 0.0, 1200.0)
        temp_air = temp_k - 273.15
        wind_speed = np.sqrt(u**2 + v**2)
        out[f"node_{node.node_id}_solar_mw"] = solar_power_pvlib(
            ghi, temp_air, wind_speed, times_utc, node
        )
        out[f"node_{node.node_id}_ghi_wm2"] = ghi
    return pd.DataFrame(out)


def load_profile() -> pd.DataFrame:
    path = LOAD_DIR / "load_2023.csv"
    if not path.exists():
        raise FileNotFoundError(path)
    df = pd.read_csv(path)
    if "load_mw" not in df.columns:
        raise KeyError("load_2023.csv must contain load_mw")
    if len(df) < 8760:
        raise ValueError(f"load CSV has {len(df)} rows, expected 8760")
    return df.iloc[:8760].copy()


def node_params_struct() -> dict:
    capacities = np.array([node.capacity_mw for node in ALL_NODES], dtype=float)
    p_min = np.array([0.0, 0.0, 0.0, 0.0, -30.0, 0.0], dtype=float)
    p_max = capacities.copy()
    p_max[4] = 30.0
    cost_a = np.array([0.000, 0.000, 0.000, 0.000, 0.010, 0.020], dtype=float)
    cost_b = np.array([0.000, 0.000, 0.000, 0.000, 1.500, 2.000], dtype=float)
    latitude = np.array([np.nan if node.latitude is None else node.latitude for node in ALL_NODES])
    longitude = np.array([np.nan if node.longitude is None else node.longitude for node in ALL_NODES])
    return {
        "node_id": np.array([node.node_id for node in ALL_NODES], dtype=np.int32),
        "type": np.array([node.kind for node in ALL_NODES], dtype=object),
        "capacity_mw": capacities,
        "cost_a": cost_a,
        "cost_b": cost_b,
        "p_min_mw": p_min,
        "p_max_mw": p_max,
        "latitude": latitude,
        "longitude": longitude,
    }


def build_mat_dict(P_solar: np.ndarray, P_wind: np.ndarray, P_load: np.ndarray) -> dict:
    return {
        "P_solar": np.asarray(P_solar, dtype=float),
        "P_wind": np.asarray(P_wind, dtype=float),
        "P_load": np.asarray(P_load, dtype=float).reshape(-1, 1),
        "node_params": node_params_struct(),
        "T": np.array([[len(P_load)]], dtype=np.int32),
        "N": np.array([[6]], dtype=np.int32),
    }


def save_mat(path: Path, P_solar: np.ndarray, P_wind: np.ndarray, P_load: np.ndarray) -> None:
    sio.savemat(path, build_mat_dict(P_solar, P_wind, P_load), do_compression=True)


def summarize_mat(path: Path) -> None:
    data = sio.loadmat(path, squeeze_me=False)
    dims = {
        "P_solar": data["P_solar"].shape,
        "P_wind": data["P_wind"].shape,
        "P_load": data["P_load"].shape,
        "T": data["T"].shape,
        "N": data["N"].shape,
        "node_params": data["node_params"].shape,
    }
    log(f"[MAT] {path}")
    for key, shape in dims.items():
        log(f"      {key}: {shape}")


def main() -> None:
    ensure_dirs()
    wind_path = ERA5_DIR / "wind_2023.nc"
    solar_path = ERA5_DIR / "solar_2023.nc"
    if not wind_path.exists() or not solar_path.exists():
        raise FileNotFoundError("ERA5 NetCDF files are missing; run scripts/download_data.py first")

    with Era5Dataset(wind_path) as wind_ds, Era5Dataset(solar_path) as solar_ds:
        times_utc = wind_ds.time_index()
        wind_df = preprocess_wind(wind_ds)
        solar_df = preprocess_solar(solar_ds, wind_ds, times_utc)

    load_df = load_profile()
    timestamps = times_utc.tz_convert(None)
    solar_df.insert(0, "timestamp_utc", timestamps.strftime("%Y-%m-%d %H:%M:%S"))
    wind_df.insert(0, "timestamp_utc", timestamps.strftime("%Y-%m-%d %H:%M:%S"))
    solar_csv = SOLAR_OUT_DIR / "solar_power_2023.csv"
    wind_csv = WIND_OUT_DIR / "wind_power_2023.csv"
    solar_df.to_csv(solar_csv, index=False)
    wind_df.to_csv(wind_csv, index=False)

    P_solar = solar_df[["node_1_solar_mw", "node_2_solar_mw"]].to_numpy()
    P_wind = wind_df[["node_3_wind_mw", "node_4_wind_mw"]].to_numpy()
    P_load = load_df["load_mw"].to_numpy().reshape(-1, 1)

    if P_solar.shape != (8760, 2) or P_wind.shape != (8760, 2) or P_load.shape != (8760, 1):
        raise ValueError(
            f"unexpected shapes: solar={P_solar.shape}, wind={P_wind.shape}, load={P_load.shape}"
        )

    full_mat = MATLAB_OUT_DIR / "vpp_dataset.mat"
    week_mat = MATLAB_OUT_DIR / "vpp_typical_week.mat"
    day_mat = MATLAB_OUT_DIR / "vpp_typical_day.mat"

    save_mat(full_mat, P_solar, P_wind, P_load)
    week_start = pd.Timestamp("2023-07-17 00:00:00")
    start_idx = int((week_start - pd.Timestamp("2023-01-01 00:00:00")).total_seconds() // 3600)
    week_slice = slice(start_idx, start_idx + 168)
    day_slice = slice(start_idx + 48, start_idx + 72)
    save_mat(week_mat, P_solar[week_slice], P_wind[week_slice], P_load[week_slice])
    save_mat(day_mat, P_solar[day_slice], P_wind[day_slice], P_load[day_slice])

    log("[CSV] Processed CSV files:")
    log(f"      {solar_csv} shape={solar_df.shape}")
    log(f"      {wind_csv} shape={wind_df.shape}")
    log("[MAT] MATLAB files and dimensions:")
    for path in (full_mat, week_mat, day_mat):
        summarize_mat(path)
    log("[DONE] Preprocessing complete.")


if __name__ == "__main__":
    main()
