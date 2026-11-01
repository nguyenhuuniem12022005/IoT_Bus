import json

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.security import create_token
from app.database import create_indexes


@pytest.mark.asyncio
async def test_health_static_and_history(client, app, telemetry, vision):
    assert (await client.get("/api/health")).json()["status"] == "ok"
    assert (await client.get("/")).status_code == 200
    assert (await client.get("/login.html")).status_code == 200
    headers = {"Authorization": "Bearer " + create_token("viewer", app.state.settings)}
    assert (await client.get("/api/buses", headers=headers)).json()[0]["sensor_online"] is False
    for suffix, data in (("sensor/telemetry", telemetry), ("vision/count", vision)):
        await app.state.handler.handle(f"smartbus/bus01/{suffix}", json.dumps(data).encode())
    rows = (await client.get("/api/buses/bus01/history", headers=headers)).json()
    assert len(rows) == 2 and rows[-1]["vision_count"] == 2
    assert rows == sorted(rows, key=lambda x: x["ts"])
    assert (await client.get("/api/buses/bus01/history?limit=0", headers=headers)).status_code == 422


@pytest.mark.asyncio
async def test_ack_does_not_close_alert(client, app, alert):
    await app.state.handler.handle("smartbus/bus01/alert", json.dumps(alert).encode())
    headers = {"Authorization": "Bearer " + create_token("operator", app.state.settings)}
    response = await client.post("/api/alerts/bus01-1000/ack", json={"note": "Đã kiểm tra"}, headers=headers)
    assert response.json()["status"] == "ACTIVE"
    assert response.json()["acknowledged_by"] == "operator"
    assert (await client.post("/api/alerts/missing/ack", json={}, headers=headers)).status_code == 404


@pytest.mark.asyncio
async def test_websocket_auth_initial_state(app):
    client = TestClient(app)
    with pytest.raises(WebSocketDisconnect) as error:
        with client.websocket_connect("/ws?token=invalid"):
            pass
    assert error.value.code == 4401
    token = create_token("viewer", app.state.settings)
    with client.websocket_connect(f"/ws?token={token}") as socket:
        message = socket.receive_json()
        assert message["type"] == "state" and message["bus_id"] == "bus01"
        assert message["data"]["vision_online"] is False


@pytest.mark.asyncio
async def test_indexes_use_datetime_ttl(app):
    await create_indexes(app.state.db, app.state.settings)
    assert ("received_at", {"expireAfterSeconds": 604800}) in app.state.db.telemetry.indexes
    assert ("alert_id", {"unique": True}) in app.state.db.alerts.indexes
