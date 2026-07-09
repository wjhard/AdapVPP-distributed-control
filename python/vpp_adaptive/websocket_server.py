from __future__ import annotations

import json
import inspect
from typing import Any, Awaitable, Callable, Set


MessageHandler = Callable[[dict], dict | Awaitable[dict | None] | None]


class TelemetryWebSocketServer:
    """Small WebSocket broadcaster for the future Vue3 frontend."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        on_message: MessageHandler | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.on_message = on_message
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
                async for raw in websocket:
                    response = await self._handle_message(raw)
                    if response is not None:
                        await websocket.send(json.dumps(response, ensure_ascii=False))
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

    async def _handle_message(self, raw: str) -> dict | None:
        if self.on_message is None:
            return {
                "message_type": "manual_control_response",
                "ok": False,
                "status": "rejected",
                "message": "websocket command channel is not configured",
            }
        try:
            message = json.loads(raw)
        except Exception as exc:
            return {
                "message_type": "manual_control_response",
                "ok": False,
                "status": "bad_json",
                "message": f"invalid websocket command: {exc}",
            }
        if not isinstance(message, dict):
            return {
                "message_type": "manual_control_response",
                "ok": False,
                "status": "bad_message",
                "message": "websocket command must be a JSON object",
            }
        result = self.on_message(message)
        if inspect.isawaitable(result):
            result = await result
        return result

    async def stop(self) -> None:
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()
