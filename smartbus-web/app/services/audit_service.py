import time
from typing import Any


def now_ms() -> int:
    return int(time.time() * 1000)


async def write_audit(db: Any, actor: str, action: str, detail: dict[str, Any]) -> None:
    await db.audit_logs.insert_one({"ts": now_ms(), "actor": actor, "action": action, "detail": detail})
