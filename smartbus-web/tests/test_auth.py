import pytest
import logging
from jose import jwt

from app.core.security import create_token, seed_users
from app.core.logging import TokenFilter


def test_websocket_token_is_removed_from_logs():
    record = logging.LogRecord("uvicorn.error", logging.INFO, "", 0,
        'WebSocket %s [accepted]', ('/ws?token=secret.jwt.value',), None)
    assert TokenFilter().filter(record)
    assert "secret.jwt.value" not in record.getMessage()
    assert "[REDACTED]" in record.getMessage()


@pytest.mark.asyncio
async def test_login_me_audit_and_no_hash(client, app):
    response = await client.post("/api/auth/login", json={"username": "admin", "password": "test-password"})
    assert response.status_code == 200
    data = response.json()
    assert data["role"] == "admin" and data["expires_in"] == 3600
    assert "password_hash" not in data
    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {data['access_token']}"})
    assert me.json() == {"username": "admin", "role": "admin"}
    assert await app.state.db.audit_logs.find_one({"action": "LOGIN"})


@pytest.mark.asyncio
async def test_invalid_login_and_expired_token(client, app):
    assert (await client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})).status_code == 401
    assert (await client.get("/api/buses")).status_code == 401
    expired = jwt.encode({"sub": "admin", "exp": 1}, app.state.settings.jwt_secret, algorithm="HS256")
    for token in (expired, "garbage"):
        assert (await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})).status_code == 401


@pytest.mark.asyncio
async def test_rbac_on_server(client, app):
    def headers(role):
        return {"Authorization": "Bearer " + create_token(role, app.state.settings)}
    assert (await client.post("/api/buses/bus01/commands", headers=headers("viewer"), json={"target": "sensor", "action": "FAN_OFF"})).status_code == 403
    assert (await client.get("/api/audit-logs", headers=headers("operator"))).status_code == 403
    assert (await client.post("/api/buses/bus01/commands", headers=headers("operator"), json={"target": "vision", "action": "PAUSE"})).status_code == 403
    assert (await client.post("/api/buses/bus01/commands", headers=headers("admin"), json={"target": "vision", "action": "PAUSE"})).status_code == 202


@pytest.mark.asyncio
async def test_seed_idempotent(app):
    await seed_users(app.state.db, app.state.settings)
    count = await app.state.db.users.count_documents({})
    await seed_users(app.state.db, app.state.settings)
    assert await app.state.db.users.count_documents({}) == count
    assert (await app.state.db.users.find_one({"username": "admin"}))["role"] == "admin"
