import asyncio
from copy import deepcopy
from typing import Any

from app.config import Settings
from app.services.audit_service import now_ms
from app.services.ws_manager import WSManager

SENSOR_FIELDS = ("ir_count", "ignition", "pir_motion", "safety_confirmed", "state", "alert_level",
                 "buzzer", "led", "fan", "presence", "wifi_rssi")


class StateService:
    def __init__(self, db: Any, ws: WSManager, settings: Settings) -> None:
        self.db, self.ws, self.settings = db, ws, settings
        self.states: dict[str, dict[str, Any]] = {}
        self.locks: dict[str, asyncio.Lock] = {}
        self.last_count: dict[str, int] = {}
        for bus_id in settings.bus_ids:
            self.get(bus_id)

    def lock(self, bus_id: str) -> asyncio.Lock:
        return self.locks.setdefault(bus_id, asyncio.Lock())

    def get(self, bus_id: str) -> dict[str, Any]:
        if bus_id not in self.states:
            self.states[bus_id] = dict(bus_id=bus_id, updated_at=0, sensor_online=False,
                vision_online=False, sensor_updated_at=0, vision_updated_at=0,
                ir_count=0, vision_count=0, vision_fresh=False, count_mismatch=False,
                state="SAFE", alert_level="NONE", ignition=False, pir_motion=False,
                safety_confirmed=False, buzzer=False, led="off", fan=False,
                presence={"pir": False, "ir": False, "vision": False}, wifi_rssi=None,
                vision_fps=0, active_alert_id=None)
        return deepcopy(self.states[bus_id])

    async def restore(self) -> None:
        for record in await self.db.bus_state.find({}, {"_id": 0}).to_list(length=None):
            bus_id = record["bus_id"]
            self.get(bus_id)
            record.update(sensor_online=False, vision_online=False, vision_fresh=False, count_mismatch=False)
            self.states[bus_id].update(record)
            await self.db.bus_state.update_one({"bus_id": bus_id}, {"$set": {
                key: False for key in ("sensor_online", "vision_online", "vision_fresh", "count_mismatch")}})

    async def patch(self, bus_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        # Người gọi giữ khóa của xe; chỉ ghi những trường đã thay đổi.
        self.get(bus_id)
        state = self.states[bus_id]
        state.update(fields)
        fresh = bus_id in self.last_count and now_ms() - self.last_count[bus_id] <= self.settings.vision_stale_s * 1000
        derived = {"vision_fresh": fresh, "count_mismatch": fresh and abs(state["ir_count"] - state["vision_count"]) >= 2,
                   "updated_at": now_ms()}
        state.update(derived)
        await self.db.bus_state.update_one({"bus_id": bus_id}, {"$set": {**fields, **derived},
            "$setOnInsert": {k: v for k, v in state.items() if k not in fields and k not in derived}}, upsert=True)
        return deepcopy(state)

    async def telemetry(self, data: dict[str, Any]) -> dict[str, Any]:
        bus_id = data["bus_id"]
        async with self.lock(bus_id):
            state = await self.patch(bus_id, {**{k: data[k] for k in SENSOR_FIELDS},
                "sensor_online": True, "sensor_updated_at": now_ms()})
            await self.ws.broadcast("state", bus_id, state)
            return state

    async def vision(self, data: dict[str, Any]) -> dict[str, Any]:
        bus_id = data["bus_id"]
        async with self.lock(bus_id):
            self.last_count[bus_id] = now_ms()
            state = await self.patch(bus_id, {"vision_count": data["person_count"], "vision_fps": data["fps"],
                "vision_online": True, "vision_updated_at": now_ms()})
            await self.ws.broadcast("vision", bus_id, data)
            await self.ws.broadcast("state", bus_id, state)
            return state

    async def status(self, data: dict[str, Any]) -> None:
        bus_id, node = data["bus_id"], data["node"]
        async with self.lock(bus_id):
            fields = {f"{node}_online": data["online"]}
            # Status không làm mới đồng hồ telemetry/count đang có.
            if not self.get(bus_id)[f"{node}_updated_at"]:
                fields[f"{node}_updated_at"] = now_ms()
            state = await self.patch(bus_id, fields)
            await self.ws.broadcast("node_status", bus_id, {k: state[k] for k in ("sensor_online", "vision_online")})

    async def expire(self) -> None:
        for bus_id in list(self.states):
            async with self.lock(bus_id):
                state = self.get(bus_id)
                fields = {f"{node}_online": False for node in ("sensor", "vision")
                    if state[f"{node}_online"] and now_ms() - state[f"{node}_updated_at"] > self.settings.node_offline_after_s * 1000}
                stale = state["vision_fresh"] and now_ms() - self.last_count.get(bus_id, 0) > self.settings.vision_stale_s * 1000
                if fields or stale:
                    state = await self.patch(bus_id, fields)
                    if fields:
                        await self.ws.broadcast("node_status", bus_id, {k: state[k] for k in ("sensor_online", "vision_online")})
                    await self.ws.broadcast("state", bus_id, state)
