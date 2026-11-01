from typing import Literal

from fastapi import APIRouter, Depends, Query, Request

from app.core.security import current_user, require_role
from app.models.schemas import AlertAckRequest

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("")
async def alerts(request: Request, bus_id: str | None = None, status: Literal["ACTIVE", "CLOSED"] | None = None,
                 limit: int = Query(50, ge=1, le=1000), user: dict = Depends(current_user)) -> list[dict]:
    query = {k: v for k, v in {"bus_id": bus_id, "status": status}.items() if v}
    return await request.app.state.db.alerts.find(query, {"_id": 0}).sort("updated_at", -1).limit(limit).to_list(length=limit)


@router.post("/{alert_id}/ack")
async def acknowledge(alert_id: str, body: AlertAckRequest, request: Request,
                      user: dict = Depends(require_role("admin", "operator"))) -> dict:
    return await request.app.state.alerts.acknowledge(alert_id, user["username"], body.note)
