"""Giả lập giao thức và máy trạng thái; không truy cập phần cứng hay YOLO."""
import argparse
import io
from PIL import Image, ImageDraw, ImageFont
from collections import deque
import json
import logging
import os
from pathlib import Path
import signal
import sys
import threading
import time
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import paho.mqtt.client as mqtt
from app.config import Settings, get_settings
from app.core.logging import configure_logging
from app.models.schemas import CommandRequest, VisionCount

logger = logging.getLogger(__name__)


def epoch_ms() -> int:
    return int(time.time() * 1000)


class SensorMachine:
    def __init__(self, bus_id: str, emit: Callable[[str, dict, int, bool], None]) -> None:
        self.bus_id, self.emit = bus_id, emit
        self.state = "SAFE"
        self.ir_count = 0
        self.ignition = False
        self.safety_confirmed = False
        self.buzzer = False
        self.fan = False
        self.auto_fan = False
        self.fan_until = 0.0
        self.pir_until = -1.0
        self.last_pir_event = -5.0
        self.vision_count = 0
        self.vision_at = -100.0
        self.check_at = 0.0
        self.warning_at = 0.0
        self.clear_at: float | None = None
        self.alert_id: str | None = None
        self.alert_level = "NONE"
        self.reasons: list[str] = []
        self.silenced = False
        self.test_until = -1.0
        self.now = 0.0
        self.last_alert_ts = 0

    def message(self, fields: dict[str, Any]) -> dict[str, Any]:
        return {"ts": epoch_ms(), "bus_id": self.bus_id, **fields}

    def event(self, event: str, detail: dict | None = None) -> None:
        self.emit("sensor/event", self.message({"event": event, "ir_count": self.ir_count, "detail": detail or {}}), 1, False)

    def transition(self, state: str) -> None:
        if self.state != state:
            previous, self.state = self.state, state
            self.event("STATE_CHANGED", {"from": previous, "to": state})

    def set_fan(self, on: bool, source: str, duration: int = 300) -> None:
        changed = self.fan != on
        self.fan = on
        self.auto_fan = on and source == "AUTO"
        self.fan_until = self.now + min(duration, 900) if on else 0
        if changed:
            self.event("FAN_CHANGED", {"on": on, "source": source})

    def alert(self, level: str, closed_by: str | None = None) -> None:
        if self.alert_id is None:
            stamp = max(epoch_ms(), self.last_alert_ts + 1)
            self.last_alert_ts = stamp
            self.alert_id = f"{self.bus_id}-{stamp}"
        self.emit("alert", self.message({"alert_id": self.alert_id, "level": level,
            "status": "CLOSED" if closed_by else "ACTIVE", "reasons": self.reasons[:], "closed_by": closed_by}), 1, False)
        self.alert_level = "NONE" if closed_by else level
        if closed_by:
            self.alert_id = None

    def close(self, reason: str) -> None:
        if self.alert_id:
            self.alert(self.alert_level, reason)
        self.buzzer = False
        self.silenced = False
        self.clear_at = None
        if self.auto_fan:
            self.set_fan(False, "AUTO")

    def ignition_change(self, on: bool) -> None:
        if on == self.ignition:
            return
        self.ignition = on
        self.event("IGNITION_ON" if on else "IGNITION_OFF")
        self.safety_confirmed = False
        if on:
            self.close("IGNITION_ON")
            self.set_fan(False, "AUTO")
            self.transition("RUNNING")
        else:
            self.check_at = self.now
            self.transition("CHECKING")

    def safety(self) -> None:
        self.safety_confirmed = True
        self.event("SAFETY_CONFIRMED")
        self.close("SAFETY_BUTTON")
        self.transition("SAFE")

    def board(self, delta: int) -> None:
        self.ir_count = max(0, self.ir_count + delta)
        self.event("BOARD" if delta > 0 else "ALIGHT")

    def pir(self) -> None:
        self.pir_until = self.now + 30
        if self.now - self.last_pir_event >= 5:
            self.event("PIR_MOTION")
            self.last_pir_event = self.now

    def presence(self) -> dict[str, bool]:
        return {"pir": self.now <= self.pir_until, "ir": self.ir_count > 0,
                "vision": self.now - self.vision_at <= 10 and self.vision_count > 0}

    def tick(self, now: float) -> None:
        self.now = now
        if self.fan and now >= self.fan_until:
            self.set_fan(False, "AUTO" if self.auto_fan else "REMOTE")
        presence = self.presence()
        if self.state == "CHECKING" and now - self.check_at >= 30 and not self.safety_confirmed and any(presence.values()):
            self.reasons = ["SAFETY_NOT_CONFIRMED"] + [reason for source, reason in (
                ("pir", "PIR_MOTION_DETECTED"), ("ir", "IR_COUNT_POSITIVE"), ("vision", "VISION_PERSON_DETECTED")) if presence[source]]
            self.warning_at = now
            self.silenced = False
            self.transition("WARNING")
            self.alert("WARNING")
        if self.state in ("WARNING", "CRITICAL"):
            if any(presence.values()):
                if self.clear_at is not None:
                    self.warning_at = now
                self.clear_at = None
                if self.state == "WARNING" and now - self.warning_at >= 30:
                    self.transition("CRITICAL")
                    self.silenced = False
                    self.alert("CRITICAL")
                    self.set_fan(True, "AUTO")
            else:
                if self.clear_at is None:
                    self.clear_at = now
                if now - self.clear_at >= 10:
                    self.close("NO_PRESENCE")
                    self.transition("CHECKING")
        self.buzzer = (self.state in ("WARNING", "CRITICAL") and not self.silenced) or now < self.test_until

    def command(self, action: str, params: dict) -> str:
        if action == "FAN_ON":
            self.set_fan(True, "REMOTE", params["duration_s"])
        elif action == "FAN_OFF":
            self.set_fan(False, "REMOTE")
        elif action == "BUZZER_SILENCE":
            self.silenced = True
            self.buzzer = False
        elif action == "ALARM_RESET":
            if self.state in ("WARNING", "CRITICAL"):
                self.close("REMOTE_RESET")
                self.transition("SAFE")
        elif action == "RESET_COUNT":
            self.ir_count = 0
            self.event("COUNT_RESET")
        elif action == "TEST_BUZZER":
            self.test_until = self.now + 1
            self.buzzer = True
        return f"{action} accepted"

    def telemetry(self) -> dict:
        return self.message({"ir_count": self.ir_count, "ignition": self.ignition,
            "pir_motion": self.now <= self.pir_until, "safety_confirmed": self.safety_confirmed,
            "state": self.state, "alert_level": self.alert_level, "buzzer": self.buzzer,
            "led": {"RUNNING": "green", "CHECKING": "red", "SAFE": "off", "WARNING": "red_blink", "CRITICAL": "red_blink"}[self.state],
            "fan": self.fan, "presence": self.presence(), "vision_fresh": self.now - self.vision_at <= 10,
            "wifi_rssi": -61, "uptime_s": int(self.now), "fw": "1.0.0"})


class SimulatedNode(threading.Thread):
    def __init__(self, node: str, bus_id: str, scenario: str, speed: float, settings: Settings, stop: threading.Event) -> None:
        super().__init__(name=f"sim-{node}", daemon=False)
        self.node, self.bus_id, self.scenario, self.speed, self.settings, self.stop_event = node, bus_id, scenario, speed, settings, stop
        self.guard = threading.RLock()
        self.started = time.monotonic()
        self.connected = False
        self.paused = False
        self.frame_id = 0
        self.steps: set[str] = set()
        self.seen: set[str] = set()
        self.seen_order: deque[str] = deque()
        self.buffer: deque[tuple[str, dict, int, bool]] = deque(maxlen=20)
        self.stream_until = 0.0
        self.video_fps = 8.0
        self.last_video = 0.0
        self.video_info: Any = None
        self.was_streaming = False
        self.video_font: Any = None
        self.sensor = SensorMachine(bus_id, self.publish)
        username = ("esp32-" if node == "sensor" else "laptop-") + bus_id
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=username, protocol=mqtt.MQTTv311)
        # Mật khẩu riêng cho simulator; đọc trực tiếp env để không thay đổi .env.example.
        self.client.username_pw_set(username, os.getenv("SENSOR_MQTT_PASSWORD" if node == "sensor" else "VISION_MQTT_PASSWORD", settings.mqtt_password))
        if settings.mqtt_tls:
            self.client.tls_set()
        self.client.reconnect_delay_set(1, 60)
        self.client.max_queued_messages_set(20)
        self.client.will_set(f"smartbus/{bus_id}/{node}/status", json.dumps({"bus_id": bus_id, "node": node, "online": False}), qos=1, retain=True)
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message

    def now(self) -> float:
        return (time.monotonic() - self.started) * self.speed

    def publish(self, suffix: str, payload: dict, qos: int = 0, retain: bool = False) -> None:
        if self.connected:
            self.client.publish(f"smartbus/{self.bus_id}/{suffix}", json.dumps(payload), qos=qos, retain=retain)
        elif self.node == "sensor" and suffix in ("sensor/event", "alert"):
            self.buffer.append((suffix, payload, qos, retain))

    def status(self) -> None:
        fields = {"fw": "1.0.0", "ip": "127.0.0.1", "rssi": -60} if self.node == "sensor" else {
            "camera_ok": True, "fps": 0.0 if self.paused else 4.8, "model": "yolov8n", "paused": self.paused, "streaming": self.streaming()}
        self.publish(f"{self.node}/status", {"ts": epoch_ms(), "bus_id": self.bus_id, "node": self.node, "online": True, **fields}, 1, True)

    def on_connect(self, client: mqtt.Client, userdata: Any, flags: Any, reason: Any, properties: Any) -> None:
        with self.guard:
            self.connected = not reason.is_failure
            if not self.connected:
                return
            client.subscribe(f"smartbus/{self.bus_id}/cmd/{self.node}", qos=1)
            if self.node == "sensor":
                client.subscribe(f"smartbus/{self.bus_id}/vision/count", qos=0)
            self.status()
            while self.buffer:
                self.publish(*self.buffer.popleft())
            logger.info("%s connected for %s", self.node, self.bus_id)

    def on_disconnect(self, client: mqtt.Client, userdata: Any, flags: Any, reason: Any, properties: Any) -> None:
        with self.guard:
            self.connected = False
            self.video_info = None
            self.sensor.vision_at = -100.0

    def on_message(self, client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage) -> None:
        with self.guard:
            try:
                data = json.loads(message.payload)
                if message.topic.endswith("/vision/count"):
                    count = VisionCount.model_validate(data)
                    if count.bus_id == self.bus_id:
                        self.sensor.vision_count = count.person_count
                        self.sensor.vision_at = self.now()
                    return
                if not isinstance(data, dict):
                    raise ValueError("Command must be an object")
                cmd_id = data.get("cmd_id")
                if not isinstance(cmd_id, str) or not cmd_id or cmd_id in self.seen:
                    return
                self.seen.add(cmd_id)
                self.seen_order.append(cmd_id)
                if len(self.seen_order) > 1000:
                    self.seen.discard(self.seen_order.popleft())
                try:
                    if set(data) != {"cmd_id", "ts", "action", "params", "issued_by"} or type(data["ts"]) is not int or not isinstance(data["issued_by"], str):
                        raise ValueError("Invalid command envelope")
                    request = CommandRequest(target=self.node, action=data["action"], params=data["params"])
                    if self.node == "sensor":
                        detail = self.sensor.command(request.action, request.params)
                    elif request.action == 'STREAM_START':
                        if self.paused:
                            raise ValueError('Camera đang tạm dừng')
                        self.video_fps = max(1., min(15., request.params.get('fps', 8)))
                        self.stream_until = time.monotonic() + 30
                        self.status()
                        detail = 'STREAM_START accepted'
                    elif request.action == 'STREAM_STOP':
                        self.stream_until = 0
                        self.status()
                        detail = 'STREAM_STOP accepted' 
                    else:
                        self.paused = request.action == "PAUSE"
                        if self.paused:
                            self.stream_until = 0
                        self.status()
                        detail = f"{request.action} accepted"
                    ok = True
                except (ValueError, TypeError, KeyError):
                    ok, detail = False, "Invalid or unsupported command"
                self.publish("cmd/ack", {"cmd_id": cmd_id, "ts": epoch_ms(), "bus_id": self.bus_id,
                    "node": self.node, "ok": ok, "detail": detail}, 1, False)
            except (ValueError, TypeError, KeyError):
                logger.warning("Invalid simulator input")

    def person_count(self) -> int:
        return {"false_alarm": 0, "camera_only": 1, "normal": 3, "forgotten_child": 1}[self.scenario]

    def streaming(self) -> bool:
        return not self.paused and time.monotonic() < self.stream_until

    def video_tick(self) -> None:
        active = self.streaming()
        if active != self.was_streaming:
            self.was_streaming = active
            self.status()
        now = time.monotonic()
        if not active or not self.connected or now - self.last_video < 1 / self.video_fps:
            return
        if self.video_info is not None:
            try:
                if not self.video_info.is_published():
                    return
            except (ValueError, RuntimeError):
                self.video_info = None
        self.last_video = now
        image = Image.new('RGB', (480, 360), '#14232c')
        draw = ImageDraw.Draw(image)
        x = int(now * 75) % 350
        draw.rectangle((x, 100, x + 80, 280), outline='#00ff60', width=4)
        if self.video_font is None:
            for name in ('arial.ttf', 'DejaVuSans.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
                         '/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf'):
                try:
                    self.video_font = ImageFont.truetype(name, 20)
                    break
                except OSError:
                    continue
            if self.video_font is None:
                logger.error('Cần font Arial, DejaVu Sans hoặc Liberation Sans để vẽ tiếng Việt')
                return
        draw.text((12, 12), f'Người: {self.person_count()}  ' + time.strftime('%H:%M:%S'),
                  font=self.video_font, fill='white')
        output = io.BytesIO()
        image.save(output, format='JPEG', quality=60)
        self.video_info = self.client.publish(f'smartbus/{self.bus_id}/vision/frame',
                                              output.getvalue(), qos=0, retain=False)

    def once(self, key: str, when: float, action: Callable[[], None]) -> None:
        if self.now() >= when and key not in self.steps:
            action()
            self.steps.add(key)

    def scenario_tick(self) -> None:
        machine = self.sensor
        machine.now = self.now()
        self.once("on", 1, lambda: machine.ignition_change(True))
        if self.scenario == "normal":
            for i in range(5):
                self.once(f"board{i}", 2 + i, lambda: machine.board(1))
            for i in range(2):
                self.once(f"alight{i}", 7 + i, lambda: machine.board(-1))
        elif self.scenario == "forgotten_child":
            self.once("board", 2, lambda: machine.board(1))
            if machine.now >= 10 and machine.state != "SAFE":
                machine.pir()
        self.once("off", 10, lambda: machine.ignition_change(False))
        if self.scenario == "normal":
            self.once("safety", 15, machine.safety)
        elif self.scenario == "false_alarm":
            self.once("safety", 50, machine.safety)
        elif self.scenario == "camera_only":
            self.once("safety", 55, machine.safety)
        machine.tick(machine.now)

    def run(self) -> None:
        self.client.connect_async(self.settings.mqtt_host, self.settings.mqtt_port, 30)
        self.client.loop_start()
        next_data = next_status = 0.0
        try:
            while not self.stop_event.is_set():
                with self.guard:
                    now = self.now()
                    if self.node == "sensor":
                        self.scenario_tick()
                        if now >= next_data:
                            self.publish("sensor/telemetry", self.sensor.telemetry())
                            next_data = now + 2
                    elif now >= next_data and not self.paused:
                        count = self.person_count()
                        self.frame_id += 1
                        self.publish("vision/count", {"ts": epoch_ms(), "bus_id": self.bus_id, "node": "vision",
                            "person_count": count, "raw_count": count, "confidence_avg": .9 if count else None,
                            "fps": 4.8, "frame_id": self.frame_id, "model": "yolov8n"})
                        next_data = now + 1
                    if self.node == "vision":
                        self.video_tick()
                    if self.node == "vision" and now >= next_status:
                        self.status()
                        next_status = now + 10
                self.stop_event.wait(min(.02, .1 / self.speed))
        finally:
            if self.connected:
                receipt = self.client.publish(f"smartbus/{self.bus_id}/{self.node}/status",
                    json.dumps({"bus_id": self.bus_id, "node": self.node, "online": False}), qos=1, retain=True)
                try:
                    receipt.wait_for_publish(timeout=2)
                except (RuntimeError, ValueError):
                    pass
            self.client.disconnect()
            self.client.loop_stop()


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(description="Giả lập hai node SmartBus độc lập")
    parser.add_argument("--bus", default="bus01")
    parser.add_argument("--node", choices=["sensor", "vision", "both"], default="both")
    parser.add_argument("--scenario", choices=["normal", "forgotten_child", "false_alarm", "camera_only"], default="normal")
    parser.add_argument("--speed", type=float, default=1.0)
    args = parser.parse_args()
    if not 0 < args.speed <= 100:
        parser.error("--speed phải > 0 và <= 100")
    import re
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", args.bus):
        parser.error("bus_id không hợp lệ")
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    nodes = [SimulatedNode(node, args.bus, args.scenario, args.speed, get_settings(), stop)
             for node in (["sensor", "vision"] if args.node == "both" else [args.node])]
    for node in nodes:
        node.start()
    try:
        while not stop.wait(.5):
            if not all(node.is_alive() for node in nodes):
                stop.set()
    finally:
        stop.set()
        for node in nodes:
            node.join()


if __name__ == "__main__":
    main()
