import asyncio
from copy import deepcopy
from types import SimpleNamespace
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.core.security import hash_password
from app.main import create_app, wire_services


def matches(row: dict, query: dict) -> bool:
    for key, value in query.items():
        actual = row.get(key)
        if isinstance(value, dict):
            for op, operand in value.items():
                if op == "$gte" and (actual is None or actual < operand):
                    return False
                if op == "$lte" and (actual is None or actual > operand):
                    return False
        elif actual != value:
            return False
    return True


class FakeCursor:
    def __init__(self, rows: list[dict], projection: dict | None = None) -> None:
        self.rows = deepcopy(rows)
        self.projection = projection or {}

    def sort(self, key: str, direction: int) -> "FakeCursor":
        self.rows.sort(key=lambda row: row.get(key, 0), reverse=direction < 0)
        return self

    def limit(self, limit: int) -> "FakeCursor":
        self.rows = self.rows[:limit]
        return self

    async def to_list(self, length: int | None = None) -> list[dict]:
        await asyncio.sleep(0)
        return [{k: v for k, v in row.items() if self.projection.get(k) != 0} for row in self.rows[:length]]


class FakeCollection:
    def __init__(self) -> None:
        self.rows: list[dict] = []
        self.indexes: list[tuple] = []

    def find(self, query: dict, projection: dict | None = None) -> FakeCursor:
        return FakeCursor([row for row in self.rows if matches(row, query)], projection)

    async def find_one(self, query: dict, projection: dict | None = None) -> dict | None:
        rows = await self.find(query, projection).to_list(1)
        return rows[0] if rows else None

    async def insert_one(self, row: dict) -> SimpleNamespace:
        await asyncio.sleep(0)
        record = deepcopy(row)
        record["_id"] = len(self.rows) + 1
        self.rows.append(record)
        return SimpleNamespace(inserted_id=record["_id"])

    async def update_one(self, query: dict, update: dict, upsert: bool = False) -> SimpleNamespace:
        await asyncio.sleep(0)
        row = next((r for r in self.rows if matches(r, query)), None)
        inserted = row is None
        if inserted:
            if not upsert:
                return SimpleNamespace(modified_count=0)
            row = deepcopy(query)
            row.update(deepcopy(update.get("$setOnInsert", {})))
            self.rows.append(row)
        row.update(deepcopy(update.get("$set", {})))
        return SimpleNamespace(modified_count=1)

    async def count_documents(self, query: dict) -> int:
        return len([row for row in self.rows if matches(row, query)])

    async def create_index(self, keys: Any, **options: Any) -> None:
        self.indexes.append((keys, options))


class FakeDB:
    def __init__(self) -> None:
        self.collections: dict[str, FakeCollection] = {}

    def __getitem__(self, name: str) -> FakeCollection:
        return self.collections.setdefault(name, FakeCollection())

    def __getattr__(self, name: str) -> FakeCollection:
        return self[name]

    async def command(self, command: str) -> dict:
        return {"ok": 1}


class FakeBridge:
    connected = True

    def __init__(self) -> None:
        self.messages: list[tuple] = []

    def publish(self, topic: str, payload: dict) -> bool:
        self.messages.append((topic, deepcopy(payload)))
        return True


@pytest.fixture(scope="session")
def password_hash() -> str:
    return hash_password("test-password")


@pytest_asyncio.fixture
async def app(password_hash: str) -> Any:
    application = create_app()
    settings = Settings(_env_file=None, jwt_secret="test-secret-that-is-at-least-32-chars")
    wire_services(application, FakeDB(), settings)
    application.state.bridge = FakeBridge()
    application.state.commands.bridge = application.state.bridge
    for role in ("admin", "operator", "viewer"):
        await application.state.db.users.insert_one({"username": role, "role": role, "password_hash": password_hash})
    return application


@pytest_asyncio.fixture
async def client(app: Any) -> AsyncClient:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.fixture
def telemetry() -> dict:
    return {"ts": 0, "bus_id": "bus01", "ir_count": 12, "ignition": False, "pir_motion": True,
        "safety_confirmed": False, "state": "WARNING", "alert_level": "WARNING", "buzzer": True,
        "led": "red_blink", "fan": False, "presence": {"pir": True, "ir": True, "vision": False},
        "vision_fresh": True, "wifi_rssi": -61, "uptime_s": 3600, "fw": "1.0.0"}


@pytest.fixture
def vision() -> dict:
    return {"ts": 0, "bus_id": "bus01", "node": "vision", "person_count": 2, "raw_count": 3,
        "confidence_avg": .71, "fps": 4.8, "frame_id": 1234, "model": "yolov8n"}


@pytest.fixture
def alert() -> dict:
    return {"ts": 1000, "bus_id": "bus01", "alert_id": "bus01-1000", "level": "WARNING",
        "status": "ACTIVE", "reasons": ["SAFETY_NOT_CONFIRMED", "IR_COUNT_POSITIVE"], "closed_by": None}
