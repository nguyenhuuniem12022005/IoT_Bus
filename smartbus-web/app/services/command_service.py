import asyncio
import logging
from typing import Any
from uuid import uuid4

from app.models.schemas import CommandRequest
from app.services.audit_service import now_ms, write_audit
from app.services.ws_manager import WSManager

logger = logging.getLogger(__name__)


class CommandService:
    def __init__(self, db: Any, ws: WSManager, timeout_s: int) -> None:
        self.db, self.ws, self.timeout_s = db, ws, timeout_s
        self.bridge: Any = None
        self.lock = asyncio.Lock()

    def send_video(self, bus_id: str, action: str) -> bool:
        # Lệnh thuê luồng không lưu commands/Audit; Audit ghi theo người xem.
        payload = {'cmd_id': 'video-' + str(uuid4()), 'ts': now_ms(),
                   'action': action, 'params': {}, 'issued_by': 'backend-video'}
        try:
            return bool(self.bridge and self.bridge.publish(f'smartbus/{bus_id}/cmd/vision', payload))
        except Exception:
            logger.exception('Không gửi được lệnh video')
            return False

    async def send(self, bus_id: str, request: CommandRequest, actor: str) -> dict[str, str]:
        payload = {"cmd_id": str(uuid4()), "ts": now_ms(), "action": request.action,
                   "params": request.params, "issued_by": actor}
        async with self.lock:
            await self.db.commands.insert_one({**payload, "bus_id": bus_id, "target": request.target, "status": "SENT"})
            await write_audit(self.db, actor, "COMMAND_SENT", {**payload, "bus_id": bus_id, "target": request.target})
            await self.ws.broadcast("cmd_ack", bus_id, {"cmd_id": payload["cmd_id"], "status": "SENT"})
            # Không xếp hàng lệnh điều khiển khi broker mất: tránh thực thi muộn sau TIMEOUT.
            if self.bridge:
                try:
                    self.bridge.publish(f"smartbus/{bus_id}/cmd/{request.target}", payload)
                except Exception:
                    logger.warning("Command publish failed; awaiting timeout")
        return {"cmd_id": payload["cmd_id"], "status": "SENT"}

    async def acknowledge(self, data: dict[str, Any]) -> None:
        if data["cmd_id"].startswith("video-"):
            return
        async with self.lock:
            command = await self.db.commands.find_one({"cmd_id": data["cmd_id"], "bus_id": data["bus_id"],
                                                        "target": data["node"], "status": "SENT"})
            if command is None:
                return
            await self.finish(command, "ACKED_OK" if data["ok"] else "ACKED_FAIL", data)

    async def finish(self, command: dict[str, Any], status: str, ack: dict[str, Any] | None = None) -> None:
        fields = {"status": status, "updated_at": now_ms(), "ack": ack}
        await self.db.commands.update_one({"cmd_id": command["cmd_id"], "status": "SENT"}, {"$set": fields})
        await write_audit(self.db, (ack or {}).get("node", "backend"), "COMMAND_" + status,
                          {"cmd_id": command["cmd_id"], "bus_id": command["bus_id"], **fields})
        await self.ws.broadcast("cmd_ack", command["bus_id"], {**(ack or {}), "cmd_id": command["cmd_id"], "status": status})

    async def expire(self) -> None:
        async with self.lock:
            pending = await self.db.commands.find({"status": "SENT", "ts": {"$lte": now_ms() - self.timeout_s * 1000}}).to_list(length=None)
            for command in pending:
                await self.finish(command, "TIMEOUT")
