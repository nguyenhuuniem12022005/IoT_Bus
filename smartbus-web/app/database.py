from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from fastapi import Request

from app.config import Settings


def get_db(request: Request) -> AsyncIOMotorDatabase:
    return request.app.state.db


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def create_indexes(db: Any, settings: Settings) -> None:
    for collection, key in (("users", "username"), ("bus_state", "bus_id"),
                            ("alerts", "alert_id"), ("commands", "cmd_id")):
        await db[collection].create_index(key, unique=True)
    for name in ("telemetry", "events", "vision_counts"):
        await db[name].create_index([("bus_id", 1), ("ts", -1)])
        # Mongo TTL chỉ hỗ trợ BSON datetime, không hỗ trợ epoch số nguyên.
        await db[name].create_index("received_at", expireAfterSeconds=settings.telemetry_ttl_days * 86400)
    await db.alerts.create_index([("bus_id", 1), ("updated_at", -1)])
    await db.commands.create_index([("status", 1), ("ts", 1)])
    await db.audit_logs.create_index("ts")
