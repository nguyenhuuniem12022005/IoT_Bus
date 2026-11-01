from fastapi import APIRouter, Depends, Query, Request

from app.core.security import require_role

router = APIRouter(tags=["audit"])


@router.get("/api/audit-logs")
async def audit(request: Request, limit: int = Query(100, ge=1, le=1000), actor: str | None = None,
                action: str | None = None, user: dict = Depends(require_role("admin"))) -> list[dict]:
    query = {k: v for k, v in {"actor": actor, "action": action}.items() if v}
    return await request.app.state.db.audit_logs.find(query, {"_id": 0}).sort("ts", -1).limit(limit).to_list(length=limit)
