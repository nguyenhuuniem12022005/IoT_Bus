import asyncio
import json

import pytest

from app.core.security import create_token
from app.models.schemas import CommandRequest
from app.services.audit_service import now_ms


@pytest.mark.asyncio
async def test_command_publish_ack_and_wrong_node(app):
    result = await app.state.commands.send("bus01", CommandRequest(target="sensor", action="FAN_ON"), "operator")
    topic, payload = app.state.bridge.messages[0]
    assert topic == "smartbus/bus01/cmd/sensor"
    assert payload["params"] == {"duration_s": 300}
    assert set(payload) == {"cmd_id", "ts", "action", "params", "issued_by"}
    ack = {"cmd_id": result["cmd_id"], "ts": 0, "bus_id": "bus01", "node": "vision", "ok": True, "detail": "accepted"}
    await app.state.handler.handle("smartbus/bus01/cmd/ack", json.dumps(ack).encode())
    assert (await app.state.db.commands.find_one({}))["status"] == "SENT"
    ack["node"] = "sensor"
    await app.state.handler.handle("smartbus/bus01/cmd/ack", json.dumps(ack).encode())
    assert (await app.state.db.commands.find_one({}))["status"] == "ACKED_OK"
    assert await app.state.db.audit_logs.find_one({"action": "COMMAND_ACKED_OK"})


@pytest.mark.asyncio
async def test_timeout_race_single_terminal_transition(app):
    result = await app.state.commands.send("bus01", CommandRequest(target="vision", action="PAUSE"), "operator")
    await app.state.db.commands.update_one({"cmd_id": result["cmd_id"]}, {"$set": {"ts": now_ms() - 11000}})
    await asyncio.gather(app.state.commands.expire(), app.state.commands.acknowledge({"cmd_id": result["cmd_id"],
        "ts": now_ms(), "bus_id": "bus01", "node": "vision", "ok": True, "detail": "ok"}))
    rows = await app.state.db.audit_logs.find({}).to_list(None)
    assert len([row for row in rows if row["action"] in ("COMMAND_TIMEOUT", "COMMAND_ACKED_OK")]) == 1


@pytest.mark.asyncio
async def test_offline_command_times_out(app):
    app.state.commands.bridge = None
    result = await app.state.commands.send("bus01", CommandRequest(target="sensor", action="FAN_OFF"), "operator")
    await app.state.db.commands.update_one({"cmd_id": result["cmd_id"]}, {"$set": {"ts": 1}})
    await app.state.commands.expire()
    assert (await app.state.db.commands.find_one({}))["status"] == "TIMEOUT"


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [
    {"target": "vision", "action": "FAN_ON"}, {"target": "sensor", "action": "PAUSE"},
    {"target": "sensor", "action": "FAN_ON", "params": {"duration_s": 901}},
    {"target": "sensor", "action": "FAN_ON", "params": {"duration_s": True}},
    {"target": "sensor", "action": "FAN_OFF", "params": {"duration_s": 300}},
])
async def test_invalid_command_rejected(client, app, body):
    headers = {"Authorization": "Bearer " + create_token("admin", app.state.settings)}
    assert (await client.post("/api/buses/bus01/commands", json=body, headers=headers)).status_code == 422
    assert not app.state.bridge.messages
