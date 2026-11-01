import asyncio
import json

import pytest


@pytest.mark.asyncio
async def test_400_interleaved_messages_preserve_both_sources(app, telemetry, vision):
    tasks = []
    for i in range(200):
        tasks.extend([
            app.state.handler.handle("smartbus/bus01/sensor/telemetry", json.dumps({**telemetry, "ir_count": i}).encode()),
            app.state.handler.handle("smartbus/bus01/vision/count", json.dumps({**vision, "person_count": i + 10, "frame_id": i}).encode()),
        ])
    await asyncio.gather(*tasks)
    state = app.state.states.get("bus01")
    assert state["ir_count"] == 199 and state["vision_count"] == 209
    assert state["state"] == "WARNING" and state["vision_fps"] == 4.8
    assert state["sensor_online"] and state["vision_online"] and state["count_mismatch"]
    persisted = await app.state.db.bus_state.find_one({"bus_id": "bus01"})
    assert persisted["ir_count"] == 199 and persisted["vision_count"] == 209
    assert await app.state.db.telemetry.count_documents({}) == 200
    assert await app.state.db.vision_counts.count_documents({}) == 200


@pytest.mark.asyncio
async def test_two_buses_are_isolated(app, telemetry, vision):
    await asyncio.gather(
        app.state.handler.handle("smartbus/bus01/sensor/telemetry", json.dumps(telemetry).encode()),
        app.state.handler.handle("smartbus/bus02/vision/count", json.dumps({**vision, "bus_id": "bus02"}).encode()))
    assert not app.state.states.get("bus01")["vision_online"]
    assert not app.state.states.get("bus02")["sensor_online"]
