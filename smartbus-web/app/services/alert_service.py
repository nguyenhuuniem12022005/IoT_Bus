from typing import Any

from fastapi import HTTPException

from app.services.audit_service import now_ms, write_audit
from app.services.state_service import StateService


class AlertService:
    def __init__(self, db: Any, states: StateService) -> None:
        self.db, self.states = db, states

    async def receive(self, data: dict[str, Any]) -> None:
        bus_id = data["bus_id"]
        async with self.states.lock(bus_id):
            previous = await self.db.alerts.find_one({"alert_id": data["alert_id"]})
            # QoS 1 có thể gửi trùng; cảnh báo đã đóng không được mở lại bởi bản tin cũ.
            if previous and (data["ts"] < previous["ts"] or previous["status"] == "CLOSED" or
                             all(previous.get(k) == v for k, v in data.items())):
                return
            record = {**data, "updated_at": now_ms()}
            await self.db.alerts.update_one({"alert_id": data["alert_id"]}, {"$set": record,
                "$setOnInsert": {"created_at": data["ts"], "acknowledged_by": None,
                                 "acknowledged_at": None, "note": ""}}, upsert=True)
            current = self.states.get(bus_id)["active_alert_id"]
            if data["status"] == "ACTIVE" or current == data["alert_id"]:
                state = await self.states.patch(bus_id, {"active_alert_id": data["alert_id"] if data["status"] == "ACTIVE" else None})
                await self.states.ws.broadcast("state", bus_id, state)
            action = "ALERT_CREATED" if previous is None else ("ALERT_CLOSED" if data["status"] == "CLOSED" else "ALERT_UPDATED")
            await write_audit(self.db, f"esp32-{bus_id}", action, data)
            await self.states.ws.broadcast("alert", bus_id, data)

    async def acknowledge(self, alert_id: str, actor: str, note: str) -> dict[str, Any]:
        record = await self.db.alerts.find_one({"alert_id": alert_id}, {"_id": 0})
        if not record:
            raise HTTPException(404, "Không tìm thấy cảnh báo")
        async with self.states.lock(record["bus_id"]):
            fields = {"acknowledged_by": actor, "acknowledged_at": now_ms(), "note": note}
            await self.db.alerts.update_one({"alert_id": alert_id}, {"$set": fields})
            await write_audit(self.db, actor, "ALERT_ACKNOWLEDGED", {"alert_id": alert_id, **fields})
            record.update(fields)
            await self.states.ws.broadcast("alert", record["bus_id"], {k: record[k] for k in
                ("ts", "bus_id", "alert_id", "level", "status", "reasons", "closed_by")})
            return record
