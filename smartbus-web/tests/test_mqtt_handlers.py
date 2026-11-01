import json

import pytest

from app.services.audit_service import now_ms
from scripts.simulate_devices import SensorMachine


@pytest.mark.asyncio
async def test_telemetry_zero_timestamp_and_vision_ownership(app, telemetry, vision):
    h = app.state.handler
    await h.handle("smartbus/bus01/sensor/telemetry", json.dumps(telemetry).encode())
    assert not app.state.states.get("bus01")["vision_fresh"]
    assert (await app.state.db.telemetry.find_one({}))["ts"] > 0
    await h.handle("smartbus/bus01/vision/count", json.dumps(vision).encode())
    state = app.state.states.get("bus01")
    assert state["vision_fresh"] and state["count_mismatch"]
    assert state["presence"] == telemetry["presence"]
    assert state["sensor_online"] and state["vision_online"]


@pytest.mark.asyncio
async def test_invalid_payloads_ignored(app, telemetry):
    h = app.state.handler
    for payload in (b"bad-json", b"[]", b"{}", b"\xff", json.dumps({**telemetry, "ir_count": -1}).encode(),
                    json.dumps({**telemetry, "ir_count": "2"}).encode(), json.dumps({**telemetry, "bus_id": "bus02"}).encode()):
        await h.handle("smartbus/bus01/sensor/telemetry", payload)
    assert await app.state.db.telemetry.count_documents({}) == 0
    await h.handle("smartbus/bus01/sensor/telemetry", json.dumps(telemetry).encode())
    assert await app.state.db.telemetry.count_documents({}) == 1


@pytest.mark.asyncio
async def test_lwt_and_independent_offline(app, telemetry, vision):
    h = app.state.handler
    await h.handle("smartbus/bus01/sensor/telemetry", json.dumps(telemetry).encode())
    await h.handle("smartbus/bus01/vision/count", json.dumps(vision).encode())
    await h.handle("smartbus/bus01/vision/status", b'{"bus_id":"bus01","node":"vision","online":false}')
    assert app.state.states.get("bus01")["sensor_online"]
    assert not app.state.states.get("bus01")["vision_online"]
    app.state.states.states["bus01"]["sensor_updated_at"] = now_ms() - 11000
    app.state.states.last_count["bus01"] = now_ms() - 11000
    await app.state.states.expire()
    state = app.state.states.get("bus01")
    assert not state["sensor_online"] and not state["vision_fresh"] and not state["count_mismatch"]


@pytest.mark.asyncio
async def test_alert_lifecycle_duplicates_and_ack_preserved(app, alert):
    h = app.state.handler
    async def send(data):
        await h.handle("smartbus/bus01/alert", json.dumps(data).encode())
    await send(alert)
    await send(alert)
    assert await app.state.db.alerts.count_documents({}) == 1
    assert await app.state.db.audit_logs.count_documents({"action": "ALERT_CREATED"}) == 1
    await app.state.alerts.acknowledge(alert["alert_id"], "operator", "Đã liên hệ tài xế")
    await send({**alert, "ts": 2000, "level": "CRITICAL"})
    await send({**alert, "ts": 3000, "level": "CRITICAL", "status": "CLOSED", "closed_by": "REMOTE_RESET"})
    await send(alert)
    record = await app.state.db.alerts.find_one({})
    assert record["status"] == "CLOSED" and record["acknowledged_by"] == "operator"
    assert app.state.states.get("bus01")["active_alert_id"] is None


@pytest.mark.asyncio
async def test_camera_alone_never_creates_alert(app, vision):
    await app.state.handler.handle("smartbus/bus01/vision/count", json.dumps(vision).encode())
    await app.state.states.expire()
    assert not app.state.states.get("bus01")["sensor_online"]
    assert await app.state.db.alerts.count_documents({}) == 0


def machine():
    messages = []
    sensor = SensorMachine("bus01", lambda topic, data, qos, retain: messages.append((topic, data)))
    sensor.ignition_change(True)
    sensor.ignition_change(False)
    return sensor, messages


def test_simulator_false_alarm_and_safety():
    sensor, messages = machine()
    sensor.tick(31)
    assert sensor.state == "CHECKING" and not sensor.buzzer
    assert not any(topic == "alert" for topic, _ in messages)
    sensor.safety()
    sensor.ir_count = 3
    sensor.tick(100)
    assert sensor.state == "SAFE" and not sensor.buzzer


def test_simulator_forgotten_child_reset_and_fan():
    sensor, messages = machine()
    sensor.ir_count = 1
    sensor.tick(30)
    assert sensor.state == "WARNING" and sensor.buzzer
    sensor.command("BUZZER_SILENCE", {})
    sensor.tick(59)
    assert not sensor.buzzer
    sensor.tick(60)
    assert sensor.state == "CRITICAL" and sensor.fan and sensor.buzzer
    sensor.command("ALARM_RESET", {})
    assert sensor.state == "SAFE" and not sensor.fan
    alerts = [data for topic, data in messages if topic == "alert"]
    assert len({a["alert_id"] for a in alerts}) == 1
    assert alerts[-1]["closed_by"] == "REMOTE_RESET"


def test_simulator_camera_only_stale_and_no_presence():
    sensor, messages = machine()
    sensor.vision_count, sensor.vision_at = 1, 30
    sensor.tick(30)
    assert sensor.state == "WARNING" and sensor.presence()["vision"]
    assert sensor.reasons == ["SAFETY_NOT_CONFIRMED", "VISION_PERSON_DETECTED"]
    sensor.tick(41)
    sensor.tick(51)
    assert sensor.state == "CHECKING" and not sensor.buzzer
    assert [data for topic, data in messages if topic == "alert"][-1]["closed_by"] == "NO_PRESENCE"


def test_simulator_camera_safety_and_test_buzzer():
    sensor, messages = machine()
    sensor.vision_count, sensor.vision_at = 1, 30
    sensor.tick(30)
    sensor.safety()
    sensor.tick(31)
    assert sensor.state == "SAFE" and sensor.presence()["vision"] and not sensor.buzzer
    assert [data for topic, data in messages if topic == "alert"][-1]["closed_by"] == "SAFETY_BUTTON"
    sensor.command("TEST_BUZZER", {})
    sensor.tick(31.5)
    assert sensor.buzzer
    sensor.tick(32)
    assert not sensor.buzzer


