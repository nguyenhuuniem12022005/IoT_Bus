import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

State = Literal["RUNNING", "CHECKING", "WARNING", "CRITICAL", "SAFE"]
Level = Literal["NONE", "WARNING", "CRITICAL"]
Reason = Literal["SAFETY_NOT_CONFIRMED", "PIR_MOTION_DETECTED", "IR_COUNT_POSITIVE", "VISION_PERSON_DETECTED"]
SENSOR_ACTIONS = {"FAN_ON", "FAN_OFF", "BUZZER_SILENCE", "ALARM_RESET", "RESET_COUNT", "TEST_BUZZER"}
VISION_ACTIONS = {"STREAM_START", "STREAM_STOP", "PAUSE", "RESUME"}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Payload(StrictModel):
    ts: int = Field(ge=0)
    bus_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")


class Presence(StrictModel):
    pir: bool
    ir: bool
    vision: bool


class Telemetry(Payload):
    ir_count: int = Field(ge=0)
    ignition: bool
    pir_motion: bool
    safety_confirmed: bool
    state: State
    alert_level: Level
    buzzer: bool
    led: Literal["off", "green", "red", "red_blink"]
    fan: bool
    presence: Presence
    vision_fresh: bool
    wifi_rssi: int
    uptime_s: int = Field(ge=0)
    fw: str


class Event(Payload):
    event: Literal["BOARD", "ALIGHT", "IGNITION_ON", "IGNITION_OFF", "PIR_MOTION", "SAFETY_CONFIRMED", "STATE_CHANGED", "FAN_CHANGED", "COUNT_RESET"]
    ir_count: int = Field(ge=0)
    detail: dict[str, Any]

    @model_validator(mode="after")
    def validate_detail(self) -> "Event":
        states = {"RUNNING", "CHECKING", "WARNING", "CRITICAL", "SAFE"}
        if self.event == "STATE_CHANGED" and (set(self.detail) != {"from", "to"} or
                any(v not in states for v in self.detail.values() if isinstance(v, str)) or
                any(not isinstance(v, str) for v in self.detail.values())):
            raise ValueError("STATE_CHANGED cần from/to hợp lệ")
        if self.event == "FAN_CHANGED" and (set(self.detail) != {"on", "source"} or
                type(self.detail.get("on")) is not bool or self.detail.get("source") not in ("AUTO", "REMOTE")):
            raise ValueError("FAN_CHANGED cần on/source hợp lệ")
        return self


class SensorStatus(StrictModel):
    bus_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    node: Literal["sensor"]
    online: bool
    ts: int = Field(default=0, ge=0)
    fw: str | None = None
    ip: str | None = None
    rssi: int | None = None

    @model_validator(mode="after")
    def complete_online(self) -> "SensorStatus":
        if self.online and ("ts" not in self.model_fields_set or any(v is None for v in (self.fw, self.ip, self.rssi))):
            raise ValueError("Thiếu trường sensor/status online")
        return self


class VisionStatus(StrictModel):
    bus_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    node: Literal["vision"]
    online: bool
    ts: int = Field(default=0, ge=0)
    camera_ok: bool | None = None
    fps: float | None = Field(default=None, ge=0)
    model: str | None = None
    paused: bool | None = None
    streaming: bool = False

    @model_validator(mode="after")
    def complete_online(self) -> "VisionStatus":
        if self.online and ("ts" not in self.model_fields_set or any(v is None for v in (self.camera_ok, self.fps, self.model, self.paused))):
            raise ValueError("Thiếu trường vision/status online")
        return self


class Alert(Payload):
    alert_id: str = Field(min_length=1, max_length=128)
    level: Literal["WARNING", "CRITICAL"]
    status: Literal["ACTIVE", "CLOSED"]
    reasons: list[Reason]
    closed_by: Literal["SAFETY_BUTTON", "IGNITION_ON", "REMOTE_RESET", "NO_PRESENCE"] | None

    @model_validator(mode="after")
    def consistent(self) -> "Alert":
        if not self.alert_id.startswith(self.bus_id + "-"):
            raise ValueError("alert_id không khớp bus_id")
        if "SAFETY_NOT_CONFIRMED" not in self.reasons or len(set(self.reasons)) < 2:
            raise ValueError("Cảnh báo cần hai điều kiện")
        if (self.status == "ACTIVE") != (self.closed_by is None):
            raise ValueError("closed_by không khớp status")
        return self


class VisionCount(Payload):
    node: Literal["vision"]
    person_count: int = Field(ge=0)
    raw_count: int = Field(ge=0)
    confidence_avg: float | None = Field(ge=0, le=1)
    fps: float = Field(ge=0)
    frame_id: int = Field(ge=0)
    model: str


class CommandAck(Payload):
    cmd_id: str = Field(min_length=1, max_length=128)
    node: Literal["sensor", "vision"]
    ok: bool
    detail: str = Field(max_length=2048)


class LoginRequest(StrictModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=72)


class CommandRequest(StrictModel):
    target: Literal["sensor", "vision"]
    action: str
    params: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def action_params(self) -> "CommandRequest":
        if self.action not in (SENSOR_ACTIONS if self.target == "sensor" else VISION_ACTIONS):
            raise ValueError("Lệnh không thuộc node đích")
        if self.action == "FAN_ON":
            if set(self.params) - {"duration_s"}:
                raise ValueError("Tham số không hợp lệ")
            duration = self.params.get("duration_s", 300)
            if type(duration) is not int or not 1 <= duration <= 900:
                raise ValueError("duration_s phải từ 1 đến 900")
            self.params = {"duration_s": duration}
        elif self.action == 'STREAM_START':
            if set(self.params) - {'fps'} or ('fps' in self.params and
                    (type(self.params['fps']) not in (int, float) or not math.isfinite(self.params['fps']))):
                raise ValueError('fps không hợp lệ')
        elif self.params:
            raise ValueError("Lệnh này yêu cầu params rỗng")
        return self


class AlertAckRequest(StrictModel):
    note: str = Field(default="", max_length=2000)


PAYLOAD_MODELS = {"sensor/telemetry": Telemetry, "sensor/event": Event,
                  "sensor/status": SensorStatus, "vision/status": VisionStatus,
                  "alert": Alert, "vision/count": VisionCount,
                  "cmd/ack": CommandAck}
