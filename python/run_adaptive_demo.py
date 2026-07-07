from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from vpp_adaptive.demo import AdaptiveVppDemo


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run adaptive VPP communication-aware demo.")
    parser.add_argument("--duration", type=float, default=120.0, help="Demo duration in seconds.")
    parser.add_argument("--interval", type=float, default=1.0, help="Dispatch interval in seconds.")
    parser.add_argument("--host", default="127.0.0.1", help="WebSocket host.")
    parser.add_argument("--port", type=int, default=8765, help="WebSocket port.")
    parser.add_argument("--fast", action="store_true", help="Run simulated time without real-time sleeping.")
    parser.add_argument(
        "--formula",
        action="store_true",
        help="Use the formula-only Gilbert-Elliott telemetry source instead of real Toxiproxy TCP probes.",
    )
    parser.add_argument(
        "--toxiproxy",
        action="store_true",
        help="Deprecated compatibility flag. Real Toxiproxy TCP probes are now the default.",
    )
    parser.add_argument("--toxiproxy-api-port", type=int, default=8474, help="Toxiproxy management API port.")
    parser.add_argument("--force-bad-link", default=None, help="Optional link key such as 1-2 to force into Bad state.")
    parser.add_argument("--force-bad-at", type=float, default=35.0, help="Elapsed seconds when manual Bad link injection starts.")
    parser.add_argument("--force-bad-duration", type=float, default=12.0, help="Manual Bad link injection duration in seconds.")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    project_root = Path(__file__).resolve().parents[1]
    demo = AdaptiveVppDemo(
        project_root=project_root,
        duration_s=args.duration,
        interval_s=args.interval,
        websocket_host=args.host,
        websocket_port=args.port,
        realtime=not args.fast,
        use_toxiproxy=not args.formula,
        toxiproxy_api_port=args.toxiproxy_api_port,
        force_bad_link=args.force_bad_link,
        force_bad_start_s=args.force_bad_at,
        force_bad_duration_s=args.force_bad_duration,
    )
    await demo.run()


if __name__ == "__main__":
    asyncio.run(main())
