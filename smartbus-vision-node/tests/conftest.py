"""Các đối tượng giả chạy hoàn toàn trong bộ nhớ."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import queue
from collections import deque
from typing import Any
import numpy as np
import pytest
from vision_node.config import load_config


class FakeCamera:
    def __init__(self) -> None:
        self.camera_ok = True
        self.available = True
        self.frame = np.zeros((480, 640, 3), dtype=np.uint8)

    def read(self) -> tuple[bool, Any]:
        return (True, self.frame.copy()) if self.camera_ok and self.available else (False, None)


class FakePublisher:
    def __init__(self) -> None:
        self.connected = True
        self.commands: queue.Queue[Any] = queue.Queue()
        self.seen: deque[str] = deque(maxlen=32)
        self.messages: list[tuple[str, dict[str, Any]]] = []

    def publish(self, topic: str, payload: dict[str, Any]) -> bool:
        from vision_node.schemas import validate_payload
        validate_payload(topic, payload)
        if self.connected:
            self.messages.append((topic, payload))
        return self.connected

    def publish_count(self, payload: dict[str, Any]) -> bool:
        return self.publish('vision/count', payload)

    def publish_status(self, payload: dict[str, Any]) -> bool:
        return self.publish('vision/status', payload)


@pytest.fixture(autouse=True)
def isolated_dotenv(monkeypatch):
    monkeypatch.setattr("vision_node.config.dotenv_values", lambda _: {})


@pytest.fixture
def config() -> dict[str, Any]:
    result = load_config(environ={})
    result.pop("crossing", None)  # Legacy occupancy pipeline tests.
    return result


@pytest.fixture
def camera() -> FakeCamera:
    return FakeCamera()


@pytest.fixture
def publisher() -> FakePublisher:
    return FakePublisher()
