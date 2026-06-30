from __future__ import annotations

import calendar
import io
import os
import re
import shutil
import time
import zipfile
from pathlib import Path

import cdsapi
from netCDF4 import Dataset
import numpy as np
import pandas as pd
import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
os.chdir(PROJECT_ROOT)
ERA5_DIR = PROJECT_ROOT / "data" / "raw" / "era5"
LOAD_DIR = PROJECT_ROOT / "data" / "raw" / "load"

ERA5_DATASET = "reanalysis-era5-single-levels"
ERA5_AREA = [29.5, 103.5, 24.5, 109.5]  # north, west, south, east
ERA5_YEAR = "2023"
HOURS = [f"{h:02d}:00" for h in range(24)]
MONTHS = [f"{m:02d}" for m in range(1, 13)]
DAYS = [f"{d:02d}" for d in range(1, 32)]

ERCOT_PAGE_URL = "https://www.ercot.com/gridinfo/load/load_hist"
ERCOT_DIRECT_URL = "https://www.ercot.com/files/docs/2023/02/09/Native_Load_2023.zip"
ERA5_CHUNK_RETRIES = 5
ERA5_RETRY_BASE_SECONDS = 60


def log(message: str) -> None:
    print(message, flush=True)


def ensure_dirs() -> None:
    for path in (ERA5_DIR, LOAD_DIR):
        path.mkdir(parents=True, exist_ok=True)


def nc_local_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        return str(path)


def valid_netcdf(path: Path) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False
    try:
        with Dataset(nc_local_path(path)) as ds:
            return bool(ds.variables)
    except Exception:
        return False


def create_var_like(out: Dataset, name: str, var) -> object:
    kwargs = {}
    if "_FillValue" in var.ncattrs():
        kwargs["fill_value"] = var.getncattr("_FillValue")
    out_var = out.createVariable(name, var.datatype, var.dimensions, **kwargs)
    for attr in var.ncattrs():
        if attr != "_FillValue":
            out_var.setncattr(attr, var.getncattr(attr))
    return out_var


def write_var(out_var, var) -> None:
    if var.dimensions:
        out_var[:] = var[:]
    else:
        out_var.assignValue(var.getValue())


def merge_netcdf_files(source_paths: list[Path], target: Path) -> None:
    if target.exists():
        target.unlink()
    with Dataset(nc_local_path(target), "w", format="NETCDF4") as out:
        for source_index, source_path in enumerate(source_paths):
            with Dataset(nc_local_path(source_path)) as src:
                if source_index == 0:
                    for attr in src.ncattrs():
                        out.setncattr(attr, src.getncattr(attr))

                for name, dim in src.dimensions.items():
                    if name not in out.dimensions:
                        out.createDimension(name, None if dim.isunlimited() else len(dim))

                for name, var in src.variables.items():
                    if name in out.variables:
                        continue
                    out_var = create_var_like(out, name, var)
                    write_var(out_var, var)


def normalize_downloaded_netcdf(path: Path) -> None:
    if valid_netcdf(path):
        return
    if not zipfile.is_zipfile(path):
        return

    extract_dir = path.with_name(f"{path.stem}_extract")
    shutil.rmtree(extract_dir, ignore_errors=True)
    extract_dir.mkdir(parents=True, exist_ok=True)
    try:
        extracted: list[Path] = []
        with zipfile.ZipFile(path) as archive:
            for index, name in enumerate(archive.namelist()):
                if not name.lower().endswith(".nc"):
                    continue
                safe_name = f"{index:02d}_{Path(name).name}"
                out_path = extract_dir / safe_name
                with archive.open(name) as src, out_path.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
                if valid_netcdf(out_path):
                    extracted.append(out_path)
        if not extracted:
            return
        path.unlink(missing_ok=True)
        if len(extracted) == 1:
            shutil.copyfile(extracted[0], path)
        else:
            merge_netcdf_files(extracted, path)
    finally:
        shutil.rmtree(extract_dir, ignore_errors=True)


def month_days(month: int) -> list[str]:
    _, ndays = calendar.monthrange(int(ERA5_YEAR), month)
    return [f"{day:02d}" for day in range(1, ndays + 1)]


def era5_request(
    variables: list[str],
    months: list[str] | None = None,
    days: list[str] | None = None,
    new_api: bool = True,
) -> dict:
    request = {
        "product_type": ["reanalysis"],
        "variable": variables,
        "year": [ERA5_YEAR],
        "month": months or MONTHS,
        "day": days or DAYS,
        "time": HOURS,
        "area": ERA5_AREA,
    }
    if new_api:
        request["data_format"] = "netcdf"
        request["download_format"] = "unarchived"
    else:
        request["format"] = "netcdf"
    return request


def download_era5_request(
    client: cdsapi.Client,
    label: str,
    variables: list[str],
    target: Path,
    months: list[str],
    days: list[str],
) -> None:
    if valid_netcdf(target):
        log(f"[ERA5] Existing valid chunk, skipping: {target}")
        return

    if target.exists():
        target.unlink()

    errors: list[str] = []
    for new_api in (True, False):
        request = era5_request(variables, months=months, days=days, new_api=new_api)
        try:
            result = client.retrieve(ERA5_DATASET, request, str(target))
            if not target.exists() and hasattr(result, "download"):
                result.download(str(target))
            normalize_downloaded_netcdf(target)
            if valid_netcdf(target):
                log(f"[ERA5] Finished {label}: {target}")
                return
            errors.append("download completed but target is not a valid NetCDF")
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
            if target.exists():
                target.unlink()

    joined = "\n".join(f"  - {err}" for err in errors)
    raise RuntimeError(f"ERA5 {label} download failed:\n{joined}")


def combine_era5_chunks(label: str, chunk_paths: list[Path], target: Path) -> None:
    log(f"[ERA5] Combining {len(chunk_paths)} monthly {label} chunks into {target}")
    if target.exists():
        target.unlink()

    with Dataset(nc_local_path(chunk_paths[0])) as first, Dataset(
        nc_local_path(target), "w", format="NETCDF4"
    ) as out:
        time_dim = "valid_time" if "valid_time" in first.dimensions else "time"
        for attr in first.ncattrs():
            out.setncattr(attr, first.getncattr(attr))

        for name, dim in first.dimensions.items():
            out.createDimension(name, None if name == time_dim else len(dim))

        out_vars = {}
        for name, var in first.variables.items():
            kwargs = {}
            if "_FillValue" in var.ncattrs():
                kwargs["fill_value"] = var.getncattr("_FillValue")
            out_var = out.createVariable(name, var.datatype, var.dimensions, **kwargs)
            for attr in var.ncattrs():
                if attr != "_FillValue":
                    out_var.setncattr(attr, var.getncattr(attr))
            out_vars[name] = out_var

        cursor = 0
        for chunk_path in chunk_paths:
            with Dataset(nc_local_path(chunk_path)) as src:
                n_time = len(src.dimensions[time_dim])
                for name, var in src.variables.items():
                    out_var = out_vars[name]
                    if time_dim in var.dimensions:
                        if var.dimensions.index(time_dim) != 0:
                            raise RuntimeError(f"{name} has unsupported time dimension order")
                        out_var[cursor : cursor + n_time, ...] = var[:]
                    elif cursor == 0:
                        if var.dimensions:
                            out_var[:] = var[:]
                        else:
                            out_var.assignValue(var.getValue())
                cursor += n_time

    if not valid_netcdf(target):
        raise RuntimeError(f"combined ERA5 {label} file is not a valid NetCDF: {target}")
    log(f"[ERA5] Finished {label}: {target}")


def retrieve_era5(label: str, variables: list[str], target: Path) -> None:
    if valid_netcdf(target):
        log(f"[ERA5] Existing valid file, skipping: {target}")
        return

    if target.exists():
        target.unlink()

    chunk_dir = ERA5_DIR / "_chunks" / label
    chunk_dir.mkdir(parents=True, exist_ok=True)
    chunk_paths: list[Path] = []
    for month in range(1, 13):
        month_str = f"{month:02d}"
        chunk_path = chunk_dir / f"{label}_{ERA5_YEAR}_{month_str}.nc"
        log(f"[ERA5] Downloading {label} {ERA5_YEAR}-{month_str} to {chunk_path}")
        for attempt in range(1, ERA5_CHUNK_RETRIES + 1):
            try:
                client = cdsapi.Client()
                download_era5_request(
                    client,
                    f"{label} {ERA5_YEAR}-{month_str}",
                    variables,
                    chunk_path,
                    months=[month_str],
                    days=month_days(month),
                )
                break
            except RuntimeError as exc:
                message = str(exc)
                fatal_tokens = ("required licences not accepted", "cost limits exceeded")
                if any(token in message for token in fatal_tokens) or attempt == ERA5_CHUNK_RETRIES:
                    raise
                wait_seconds = ERA5_RETRY_BASE_SECONDS * attempt
                log(
                    f"[ERA5] {label} {ERA5_YEAR}-{month_str} failed on attempt "
                    f"{attempt}/{ERA5_CHUNK_RETRIES}; retrying in {wait_seconds}s"
                )
                log(f"[ERA5] Last error: {message.splitlines()[-1]}")
                time.sleep(wait_seconds)
        chunk_paths.append(chunk_path)

    combine_era5_chunks(label, chunk_paths, target)


def find_ercot_zip_url() -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
    }
    try:
        response = requests.get(ERCOT_PAGE_URL, headers=headers, timeout=30)
        response.raise_for_status()
        html = response.text
        match = re.search(r'href="([^"]*Native_Load_2023\.zip)"', html, flags=re.I)
        if match:
            href = match.group(1)
            if href.startswith("http"):
                return href
            return "https://www.ercot.com" + href
    except Exception as exc:
        log(f"[LOAD] Could not inspect ERCOT page: {exc}")
    return ERCOT_DIRECT_URL


def download_ercot_zip(target: Path) -> bool:
    url = find_ercot_zip_url()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36",
        "Accept": "application/zip,application/octet-stream,*/*",
        "Referer": ERCOT_PAGE_URL,
    }
    try:
        log(f"[LOAD] Downloading ERCOT load ZIP: {url}")
        response = requests.get(url, headers=headers, timeout=90)
        response.raise_for_status()
        if len(response.content) < 1024:
            raise RuntimeError("downloaded payload is too small")
        target.write_bytes(response.content)
        if not zipfile.is_zipfile(target):
            raise RuntimeError("downloaded payload is not a ZIP archive")
        log(f"[LOAD] ERCOT ZIP saved: {target}")
        return True
    except Exception as exc:
        log(f"[LOAD] ERCOT download failed, using synthetic load fallback: {exc}")
        if target.exists():
            target.unlink()
        return False


def read_ercot_zip(path: Path) -> pd.Series:
    candidates: list[pd.DataFrame] = []
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            lower = name.lower()
            if lower.endswith((".xlsx", ".xlsm")):
                with archive.open(name) as member:
                    sheets = pd.read_excel(io.BytesIO(member.read()), sheet_name=None)
                candidates.extend(sheets.values())
            elif lower.endswith((".csv", ".txt")):
                with archive.open(name) as member:
                    candidates.append(pd.read_csv(member))

    for df in candidates:
        if len(df) < 8000:
            continue
        df = df.copy()
        df.columns = [str(col).strip() for col in df.columns]
        upper = {col.upper(): col for col in df.columns}
        load_col = None
        for name in ("ERCOT", "TOTAL", "LOAD"):
            if name in upper:
                load_col = upper[name]
                break
        if load_col is not None:
            series = pd.to_numeric(df[load_col], errors="coerce")
        else:
            numeric = df.apply(pd.to_numeric, errors="coerce")
            numeric = numeric.loc[:, numeric.notna().sum() >= 8000]
            numeric = numeric.loc[:, numeric.max(skipna=True) > 1000]
            if numeric.shape[1] == 0:
                continue
            if numeric.shape[1] == 1:
                series = numeric.iloc[:, 0]
            else:
                series = numeric.sum(axis=1)
        series = series.dropna().astype(float)
        if len(series) >= 8760 and series.max() > 1000:
            return series.iloc[:8760].reset_index(drop=True)

    raise RuntimeError("could not find an hourly ERCOT load series in ZIP")


def synthetic_south_china_load() -> pd.Series:
    index = pd.date_range("2023-01-01 00:00:00", periods=8760, freq="h")
    daily_shape = np.array(
        [
            0.58,
            0.55,
            0.53,
            0.52,
            0.53,
            0.58,
            0.66,
            0.75,
            0.82,
            0.86,
            0.88,
            0.90,
            0.89,
            0.87,
            0.86,
            0.88,
            0.92,
            0.98,
            1.00,
            0.96,
            0.89,
            0.78,
            0.68,
            0.62,
        ],
        dtype=float,
    )
    hours = index.hour.to_numpy()
    day_of_year = index.dayofyear.to_numpy()
    seasonal = 1.0 + 0.14 * np.cos(2 * np.pi * (day_of_year - 205) / 365.0)
    seasonal += 0.06 * np.cos(4 * np.pi * (day_of_year - 20) / 365.0)
    weekday_factor = np.where(index.dayofweek.to_numpy() >= 5, 0.94, 1.0)
    rng = np.random.default_rng(20230629)
    small_variation = 1.0 + rng.normal(0.0, 0.015, len(index))
    values = daily_shape[hours] * seasonal * weekday_factor * small_variation
    values = np.clip(values, 0.35, None)
    return pd.Series(values, name="load_raw")


def save_load_csv(raw_load: pd.Series, source: str, target: Path) -> None:
    index = pd.date_range("2023-01-01 00:00:00", periods=8760, freq="h")
    raw = raw_load.astype(float).to_numpy()
    if len(raw) < 8760:
        raise ValueError("load series has fewer than 8760 samples")
    raw = raw[:8760]
    load_pu = raw / np.nanmax(raw)
    load_pu = np.clip(load_pu, 0.0, 1.0)
    load_mw = load_pu * 80.0
    out = pd.DataFrame(
        {
            "timestamp": index.strftime("%Y-%m-%d %H:%M:%S"),
            "load_pu": load_pu,
            "load_mw": load_mw,
            "source": source,
        }
    )
    out.to_csv(target, index=False)
    log(f"[LOAD] Load CSV saved: {target}")
    log(f"[LOAD] Shape: {out.shape}, peak_mw={out['load_mw'].max():.3f}")


def build_load() -> None:
    load_csv = LOAD_DIR / "load_2023.csv"
    if load_csv.exists() and len(pd.read_csv(load_csv)) == 8760:
        log(f"[LOAD] Existing 8760-hour load CSV, skipping: {load_csv}")
        return

    zip_path = LOAD_DIR / "ercot_native_load_2023.zip"
    if download_ercot_zip(zip_path):
        try:
            load = read_ercot_zip(zip_path)
            save_load_csv(load, "ERCOT Native_Load_2023", load_csv)
            return
        except Exception as exc:
            log(f"[LOAD] ERCOT parse failed, using synthetic fallback: {exc}")

    load = synthetic_south_china_load()
    save_load_csv(load, "Synthetic South China Grid typical load", load_csv)


def main() -> None:
    ensure_dirs()
    retrieve_era5(
        "wind",
        [
            "10m_u_component_of_wind",
            "10m_v_component_of_wind",
            "100m_u_component_of_wind",
            "100m_v_component_of_wind",
        ],
        ERA5_DIR / "wind_2023.nc",
    )
    retrieve_era5(
        "solar",
        ["surface_solar_radiation_downwards", "2m_temperature"],
        ERA5_DIR / "solar_2023.nc",
    )
    build_load()

    log("[DONE] Raw data stage complete.")
    for path in (
        ERA5_DIR / "wind_2023.nc",
        ERA5_DIR / "solar_2023.nc",
        LOAD_DIR / "load_2023.csv",
    ):
        log(f"  {path} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
