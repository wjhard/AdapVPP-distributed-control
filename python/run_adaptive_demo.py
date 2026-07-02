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
    )
    await demo.run()


if __name__ == "__main__":
    asyncio.run(main())
