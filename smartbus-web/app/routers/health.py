from fastapi import APIRouter, Request

from app.services.audit_service import now_ms

router = APIRouter(tags=["health"])


@router.get("/api/health")
async def health(request: Request) -> dict:
    try:
        await request.app.state.db.command("ping")
        mongo = True
    except Exception:
        mongo = False
    return {"status": "ok", "mongo": mongo, "mqtt": bool(request.app.state.bridge.connected), "time": now_ms()}
