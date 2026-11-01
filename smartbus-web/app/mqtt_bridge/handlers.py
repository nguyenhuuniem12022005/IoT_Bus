import json
import logging
from typing import Any

from app.database import utc_now
from app.models.schemas import PAYLOAD_MODELS
from app.services.audit_service import now_ms

logger = logging.getLogger(__name__)


class MessageHandler:
    def __init__(self, db: Any, states: Any, alerts: Any, commands: Any, ws: Any, video: Any = None) -> None:
        self.video = video
        self.db, self.states, self.alerts, self.commands, self.ws = db, states, alerts, commands, ws

    async def handle(self, topic: str, payload: bytes) -> None:
        parts = topic.split("/")
        if len(parts) < 3 or parts[0] != "smartbus":
            return
        suffix = "/".join(parts[2:])
        if suffix == 'vision/frame':
            if self.video:
                await self.video.frame(parts[1], payload)
            return
        model = PAYLOAD_MODELS.get(suffix)
        if model is None:
            return
        try:
            if len(payload) > 100000:
                raise ValueError("Payload too large")
            data = model.model_validate(json.loads(payload)).model_dump(exclude_unset=True)
            if data["bus_id"] != parts[1]:
                raise ValueError("Topic bus mismatch")
            if not data.get("ts"):
                data["ts"] = now_ms()
        except (ValueError, TypeError, KeyError, UnicodeError):
            logger.warning("Invalid MQTT payload on %s", suffix)
            return
        try:
            await self.dispatch(suffix, data)
        except Exception:
            logger.exception("MQTT processing failed on %s", suffix)

    async def dispatch(self, suffix: str, data: dict[str, Any]) -> None:
        bus_id = data["bus_id"]
        if suffix == "sensor/telemetry":
            state = await self.states.telemetry(data)
            await self.db.telemetry.insert_one({**data, "vision_count": state["vision_count"], "received_at": utc_now()})
        elif suffix == "vision/count":
            state = await self.states.vision(data)
            await self.db.vision_counts.insert_one({**data, "ir_count": state["ir_count"], "state": state["state"], "received_at": utc_now()})
        elif suffix == "sensor/event":
            await self.db.events.insert_one({**data, "received_at": utc_now()})
            await self.ws.broadcast("event", bus_id, data)
        elif suffix.endswith("/status"):
            await self.states.status(data)
        elif suffix == "alert":
            await self.alerts.receive(data)
        elif suffix == "cmd/ack":
            await self.commands.acknowledge(data)
