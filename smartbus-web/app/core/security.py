import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import Settings

password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return password_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return password_context.verify(password, hashed)


def create_token(username: str, settings: Settings) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": username, "iat": now, "exp": now + timedelta(minutes=settings.jwt_expire_minutes)},
                      settings.jwt_secret, algorithm="HS256")


async def resolve_user(token: str, db: Any, settings: Settings) -> dict[str, Any]:
    try:
        data = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"], options={"require_exp": True, "require_sub": True})
        user = await db.users.find_one({"username": data["sub"]})
        if not user or user.get("role") not in ("viewer", "operator", "admin"):
            raise ValueError("Unknown user")
        return {"username": user["username"], "role": user["role"]}
    except (JWTError, ValueError, KeyError):
        raise HTTPException(401, "Phiên đăng nhập không hợp lệ hoặc đã hết hạn") from None


async def current_user(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict[str, Any]:
    if credentials is None:
        raise HTTPException(401, "Vui lòng đăng nhập")
    return await resolve_user(credentials.credentials, request.app.state.db, request.app.state.settings)


def require_role(*roles: str) -> Callable:
    async def dependency(user: dict = Depends(current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(403, "Bạn không có quyền thực hiện thao tác này")
        return user
    return dependency


async def seed_users(db: Any, settings: Settings, only_empty: bool = False) -> None:
    if only_empty and await db.users.count_documents({}):
        return
    for role in ("admin", "operator", "viewer"):
        username = getattr(settings, f"seed_{role}_username")
        if not await db.users.find_one({"username": username}):
            hashed = await asyncio.to_thread(hash_password, getattr(settings, f"seed_{role}_password"))
            await db.users.update_one({"username": username}, {"$setOnInsert": {
                "username": username, "role": role, "password_hash": hashed}}, upsert=True)
