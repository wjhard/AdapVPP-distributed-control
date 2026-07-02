from __future__ import annotations

import json
from typing import Any, Set


class TelemetryWebSocketServer:
    """Small WebSocket broadcaster for the future Vue3 frontend."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8765) -> None:
        self.host = host
        self.port = port
        self.clients: Set[Any] = set()
        self.server = None
        self.enabled = False
        self.error = ""

    async def start(self) -> None:
        try:
            import websockets
        except Exception as exc:
            self.enabled = False
            self.error = f"websockets package unavailable: {exc}"
            return

        async def handler(websocket: Any) -> None:
            self.clients.add(websocket)
            try:
                await websocket.wait_closed()
            finally:
                self.clients.discard(websocket)

        self.server = await websockets.serve(handler, self.host, self.port)
        self.enabled = True

    async def broadcast(self, payload: dict) -> None:
        if not self.enabled or not self.clients:
            return
        message = json.dumps(payload, ensure_ascii=False)
        dead = []
        for client in list(self.clients):
            try:
                await client.send(message)
            except Exception:
                dead.append(client)
        for client in dead:
            self.clients.discard(client)

    async def stop(self) -> None:
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()
