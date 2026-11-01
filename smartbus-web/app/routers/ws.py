import asyncio

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from app.core.security import resolve_user

router = APIRouter()


@router.websocket("/ws")
async def websocket(socket: WebSocket, token: str = "") -> None:
    app = socket.app.state
    try:
        await resolve_user(token, app.db, app.settings)
    except HTTPException:
        await socket.close(code=4401)
        return
    await app.ws.connect(socket)
    try:
        for bus_id in list(app.states.states):
            await app.ws.send(socket, {"type": "state", "bus_id": bus_id, "data": app.states.get(bus_id)})
        while True:
            try:
                await asyncio.wait_for(socket.receive_text(), timeout=15)
            except asyncio.TimeoutError:
                pass
            try:
                await resolve_user(token, app.db, app.settings)
            except HTTPException:
                await socket.close(code=4401)
                break
    except WebSocketDisconnect:
        pass
    finally:
        app.ws.disconnect(socket)
