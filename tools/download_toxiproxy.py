from __future__ import annotations

import argparse
import os
import platform
import stat
import sys
from pathlib import Path
from typing import Iterable

import requests


RELEASE_API = "https://api.github.com/repos/Shopify/toxiproxy/releases/latest"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download Shopify Toxiproxy server/CLI binaries for the local platform."
    )
    parser.add_argument("--output-dir", default="tools/toxiproxy", help="Directory for downloaded binaries.")
    parser.add_argument("--force", action="store_true", help="Redownload even when binaries already exist.")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    release = _latest_release()
    suffix = _asset_suffix()
    downloads = {
        f"toxiproxy-server-{suffix}": _server_name(),
        f"toxiproxy-cli-{suffix}": _cli_name(),
    }

    print(f"Toxiproxy release: {release['tag_name']}")
    for asset_prefix, target_name in downloads.items():
        asset = _find_asset(release["assets"], asset_prefix)
        target_path = output_dir / target_name
        if target_path.exists() and not args.force:
            print(f"exists {target_path}")
            continue
        _download(asset["browser_download_url"], target_path)
        _make_executable(target_path)
        print(f"downloaded {target_path}")

    (output_dir / "version.txt").write_text(release["tag_name"] + "\n", encoding="utf-8")


def _latest_release() -> dict:
    response = requests.get(RELEASE_API, timeout=30)
    response.raise_for_status()
    return response.json()


def _asset_suffix() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "windows":
        os_name = "windows"
        ext = ".exe"
    elif system == "linux":
        os_name = "linux"
        ext = ""
    elif system == "darwin":
        os_name = "darwin"
        ext = ""
    else:
        raise SystemExit(f"Unsupported OS for automatic Toxiproxy download: {platform.system()}")

    if machine in {"amd64", "x86_64"}:
        arch = "amd64"
    elif machine in {"arm64", "aarch64"}:
        arch = "arm64"
    else:
        raise SystemExit(f"Unsupported CPU architecture for Toxiproxy download: {platform.machine()}")

    return f"{os_name}-{arch}{ext}"


def _server_name() -> str:
    return "toxiproxy-server.exe" if platform.system().lower() == "windows" else "toxiproxy-server"


def _cli_name() -> str:
    return "toxiproxy-cli.exe" if platform.system().lower() == "windows" else "toxiproxy-cli"


def _find_asset(assets: Iterable[dict], expected_name: str) -> dict:
    for asset in assets:
        if asset["name"] == expected_name:
            return asset
    available = ", ".join(asset["name"] for asset in assets)
    raise SystemExit(f"Release asset not found: {expected_name}\nAvailable assets: {available}")


def _download(url: str, target_path: Path) -> None:
    with requests.get(url, stream=True, timeout=120) as response:
        response.raise_for_status()
        tmp_path = target_path.with_suffix(target_path.suffix + ".tmp")
        with tmp_path.open("wb") as fh:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    fh.write(chunk)
        tmp_path.replace(target_path)


def _make_executable(path: Path) -> None:
    if os.name == "nt":
        return
    mode = path.stat().st_mode
    path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


if __name__ == "__main__":
    try:
        main()
    except requests.RequestException as exc:
        print(f"Failed to download Toxiproxy: {exc}", file=sys.stderr)
        raise SystemExit(1)
