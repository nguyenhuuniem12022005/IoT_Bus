import asyncio
from typing import Any

from fastapi import WebSocket


class WSManager:
    def __init__(self) -> None:
        self.clients: dict[WebSocket, asyncio.Lock] = {}

    async def connect(self, socket: WebSocket) -> None:
        await socket.accept()
        self.clients[socket] = asyncio.Lock()

    def disconnect(self, socket: WebSocket) -> None:
        self.clients.pop(socket, None)

    async def send(self, socket: WebSocket, message: dict[str, Any]) -> None:
        lock = self.clients.get(socket)
        if lock is None:
            return
        try:
            async with lock:
                await asyncio.wait_for(socket.send_json(message), timeout=3)
        except Exception:
            self.disconnect(socket)
            try:
                await socket.close(code=1013)
            except Exception:
                pass

    async def broadcast(self, kind: str, bus_id: str, data: dict[str, Any]) -> None:
        await asyncio.gather(*(self.send(ws, {"type": kind, "bus_id": bus_id, "data": data})
                               for ws in list(self.clients)))

    async def close(self) -> None:
        for socket in list(self.clients):
            try:
                await socket.close(code=1001)
            except Exception:
                pass
            self.disconnect(socket)
