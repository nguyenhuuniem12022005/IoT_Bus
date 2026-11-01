import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.security import create_token, current_user, verify_password
from app.models.schemas import LoginRequest
from app.services.audit_service import write_audit

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
async def login(body: LoginRequest, request: Request) -> dict:
    db, settings = request.app.state.db, request.app.state.settings
    user = await db.users.find_one({"username": body.username})
    valid = user is not None and await asyncio.to_thread(verify_password, body.password, user["password_hash"])
    if not valid:
        await write_audit(db, body.username, "LOGIN_FAILED", {})
        raise HTTPException(401, "Tên đăng nhập hoặc mật khẩu không đúng")
    await write_audit(db, body.username, "LOGIN", {})
    return {"access_token": create_token(body.username, settings), "token_type": "bearer",
            "username": body.username, "role": user["role"], "expires_in": settings.jwt_expire_minutes * 60}


@router.get("/me")
async def me(user: dict = Depends(current_user)) -> dict:
    return user
