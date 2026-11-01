from fastapi import APIRouter, Depends, HTTPException, Query, Request

import asyncio
import time
from typing import Any, AsyncIterator
from fastapi.responses import JSONResponse, StreamingResponse
from app.core.security import current_user, resolve_user, bearer
from fastapi.security import HTTPAuthorizationCredentials
from app.services.video_service import mjpeg_part
from app.services.audit_service import now_ms


async def bus_user(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict[str, Any]:
    # Cookie chỉ được chấp nhận trên đúng đường dẫn video; các API khác vẫn cần Bearer.
    if credentials is None and request.url.path.endswith('/stream.mjpg'):
        return await resolve_user(request.cookies.get('video_auth', ''), request.app.state.db, request.app.state.settings)
    return await current_user(request, credentials)


router = APIRouter(prefix="/api/buses", tags=["buses"], dependencies=[Depends(bus_user)])


@router.get("")
async def buses(request: Request) -> list[dict]:
    states = request.app.state.states
    return [states.get(bus_id) for bus_id in states.states]


@router.get("/{bus_id}/state")
async def state(bus_id: str, request: Request) -> dict:
    if bus_id not in request.app.state.states.states:
        raise HTTPException(404, "Không tìm thấy xe")
    return request.app.state.states.get(bus_id)


@router.get("/{bus_id}/history")
async def history(bus_id: str, request: Request, minutes: int = Query(60, ge=1, le=10080),
                  limit: int = Query(500, ge=1, le=5000)) -> list[dict]:
    query = {"bus_id": bus_id, "ts": {"$gte": now_ms() - minutes * 60000}}
    db = request.app.state.db
    telemetry = await db.telemetry.find(query, {"_id": 0}).sort("ts", -1).limit(limit).to_list(length=limit)
    vision = await db.vision_counts.find(query, {"_id": 0}).sort("ts", -1).limit(limit).to_list(length=limit)
    rows = [{"ts": x["ts"], "ir_count": x["ir_count"], "vision_count": x["vision_count"], "state": x["state"]} for x in telemetry]
    rows += [{"ts": x["ts"], "ir_count": x["ir_count"], "vision_count": x["person_count"], "state": x["state"]} for x in vision]
    return sorted(rows, key=lambda row: row["ts"])[-limit:]


@router.get("/{bus_id}/events")
async def events(bus_id: str, request: Request, limit: int = Query(100, ge=1, le=1000)) -> list[dict]:
    return await request.app.state.db.events.find({"bus_id": bus_id}, {"_id": 0, "received_at": 0}).sort("ts", -1).limit(limit).to_list(length=limit)


@router.post("/{bus_id}/video-session")
async def video_session(bus_id: str, request: Request,
                        credentials: HTTPAuthorizationCredentials = Depends(bearer)) -> JSONResponse:
    if bus_id not in request.app.state.states.states:
        raise HTTPException(404, 'Không tìm thấy xe')
    response = JSONResponse({'ready': True})
    response.set_cookie('video_auth', credentials.credentials, httponly=True,
                        secure=request.url.scheme == 'https', samesite='strict',
                        path=f'/api/buses/{bus_id}/stream.mjpg')
    response.headers['Cache-Control'] = 'no-store'
    return response


@router.get("/{bus_id}/stream.mjpg")
async def video_stream(bus_id: str, request: Request, user: dict = Depends(bus_user)) -> StreamingResponse:
    if bus_id not in request.app.state.states.states:
        raise HTTPException(404, 'Không tìm thấy xe')
    service = request.app.state.video
    viewer = await service.add(bus_id, user['username'])
    authorization = request.headers.get('authorization', '')
    token = authorization[7:] if authorization.lower().startswith('bearer ') else request.cookies.get('video_auth', '')

    async def frames() -> AsyncIterator[bytes]:
        checked = time.monotonic()
        try:
            while not await request.is_disconnected():
                if time.monotonic() - checked >= 15:
                    await resolve_user(token, request.app.state.db, request.app.state.settings)
                    checked = time.monotonic()
                try:
                    frame = await asyncio.wait_for(viewer.queue.get(), timeout=1)
                except asyncio.TimeoutError:
                    continue
                yield mjpeg_part(frame)
        finally:
            await asyncio.shield(service.remove(bus_id, viewer))

    return StreamingResponse(frames(), media_type='multipart/x-mixed-replace; boundary=frame',
                             headers={'Cache-Control': 'no-store, no-cache', 'X-Accel-Buffering': 'no'})
