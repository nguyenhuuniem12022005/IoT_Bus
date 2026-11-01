import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.core.security import current_user, require_role
from app.models.schemas import CommandRequest

router = APIRouter(tags=["commands"])


@router.post("/api/buses/{bus_id}/commands", status_code=202)
async def send(bus_id: str, body: CommandRequest, request: Request,
               user: dict = Depends(require_role("admin", "operator"))) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", bus_id):
        raise HTTPException(422, "Mã xe không hợp lệ")
    if body.action in ("PAUSE", "RESUME") and user["role"] != "admin":
        raise HTTPException(403, "Chỉ admin được tạm dừng/tiếp tục camera")
    return await request.app.state.commands.send(bus_id, body, user["username"])


@router.get("/api/commands")
async def commands(request: Request, bus_id: str | None = None, limit: int = Query(50, ge=1, le=1000),
                   user: dict = Depends(current_user)) -> list[dict]:
    return await request.app.state.db.commands.find({"bus_id": bus_id} if bus_id else {}, {"_id": 0}).sort("ts", -1).limit(limit).to_list(length=limit)
