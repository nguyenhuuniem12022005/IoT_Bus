"""Theo dõi MQTT; cung cấp cấu hình chung cho các công cụ cùng thư mục."""
from __future__ import annotations
import json
import logging
import os
import signal
import sys
import threading
from pathlib import Path
from typing import Any
import paho.mqtt.client as mqtt
from colorama import Fore, Style, just_fix_windows_console
from dotenv import load_dotenv

# Dùng UTF-8 kể cả khi PowerShell chuyển hướng đầu ra.
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

LOG = logging.getLogger("smartbus")

def configure() -> tuple[str, int, bool, str, str, str]:
    """Đọc tệp cấu hình cạnh script, không ghi mật khẩu vào log."""
    load_dotenv(Path(__file__).with_name(".env"))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    just_fix_windows_console()
    return (os.getenv("MQTT_HOST", "localhost"), int(os.getenv("MQTT_PORT", "1883")),
            os.getenv("MQTT_TLS", "false").lower() in {"1", "true", "yes"},
            os.getenv("MQTT_USERNAME", "backend"), os.getenv("MQTT_PASSWORD", ""),
            os.getenv("BUS_ID", "bus01"))

def make_client(client_id: str, settings: tuple[str, int, bool, str, str, str]) -> mqtt.Client:
    """Tạo MQTT 3.1.1, xác minh CA mặc định khi dùng TLS."""
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id,
                         protocol=mqtt.MQTTv311)
    client.username_pw_set(settings[3], settings[4])
    if settings[2]:
        client.tls_set()
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.enable_logger(LOG)
    return client

def stop_event() -> threading.Event:
    """Đóng êm bằng Ctrl+C hoặc SIGTERM."""
    stop = threading.Event()
    def handle(signum: int, frame: Any) -> None:
        stop.set()
    signal.signal(signal.SIGINT, handle)
    signal.signal(signal.SIGTERM, handle)
    return stop

def start(client: mqtt.Client, settings: tuple[str, int, bool, str, str, str]) -> None:
    """Kết nối bất đồng bộ để lỗi broker được tự thử lại."""
    client.connect_async(settings[0], settings[1], keepalive=15)
    client.loop_start()

def redact(value: Any) -> Any:
    """Bỏ nội dung ảnh trước khi hiển thị."""
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items() if k != "image_b64"}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value

def main() -> None:
    """Theo dõi mọi topic của xe bằng tài khoản có quyền đọc."""
    settings = configure()
    client = make_client(f"monitor-{settings[5]}", settings)
    stop = stop_event()
    def connected(c: mqtt.Client, userdata: Any, flags: Any, reason: Any, properties: Any) -> None:
        if not reason.is_failure:
            c.subscribe(f"smartbus/{settings[5]}/#", qos=1)
    def received(c: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage) -> None:
        try:
            value = redact(json.loads(message.payload))
            LOG.info("%s%s%s\n%s", Fore.CYAN, message.topic, Style.RESET_ALL,
                     json.dumps(value, ensure_ascii=False, indent=2))
        except (ValueError, UnicodeError):
            LOG.warning("Payload JSON sai trên %s", message.topic)
    client.on_connect = connected
    client.on_message = received
    start(client, settings)
    try:
        while not stop.wait(0.2):
            pass
    finally:
        client.disconnect()
        client.loop_stop()

if __name__ == "__main__":
    main()
