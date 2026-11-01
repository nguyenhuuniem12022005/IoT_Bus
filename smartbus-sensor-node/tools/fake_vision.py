"""Giả lập camera độc lập, chỉ gửi số đếm mới nhất khi broker hoạt động."""
from __future__ import annotations
import argparse
import json
import time
from typing import Any
import paho.mqtt.client as mqtt
from mqtt_monitor import LOG, configure, make_client, start, stop_event

def main() -> None:
    """Phát count theo chu kỳ và status retained mỗi 10 giây."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--interval", type=float, default=1)
    args = parser.parse_args()
    if args.count < 0 or args.interval <= 0:
        parser.error("count phải >= 0; interval phải > 0")
    settings = configure()
    client = make_client(f"laptop-{settings[5]}", settings)
    stop = stop_event()
    prefix = f"smartbus/{settings[5]}/vision/"
    will = {"bus_id": settings[5], "node": "vision", "online": False}
    client.will_set(prefix + "status", json.dumps(will), qos=1, retain=True)
    def status(online: bool) -> mqtt.MQTTMessageInfo:
        payload = {"ts": time.time_ns() // 1_000_000, "bus_id": settings[5], "node": "vision",
                   "online": online, "camera_ok": online, "fps": 1 / args.interval,
                   "model": "yolov8n", "paused": False}
        return client.publish(prefix + "status", json.dumps(payload), qos=1, retain=True)
    def connected(c: mqtt.Client, userdata: Any, flags: Any, reason: Any, properties: Any) -> None:
        if not reason.is_failure:
            status(True)
            LOG.info("Camera giả kết nối, count=%d", args.count)
    client.on_connect = connected
    start(client, settings)
    frame = 0
    last_status = 0.0
    try:
        while not stop.is_set():
            if client.is_connected():
                frame += 1
                payload = {"ts": time.time_ns() // 1_000_000, "bus_id": settings[5], "node": "vision",
                           "person_count": args.count, "raw_count": args.count,
                           "confidence_avg": 0.9 if args.count else None,
                           "fps": 1 / args.interval, "frame_id": frame, "model": "yolov8n"}
                client.publish(prefix + "count", json.dumps(payload), qos=0, retain=False)
                if time.monotonic() - last_status >= 10:
                    status(True)
                    last_status = time.monotonic()
            stop.wait(args.interval)
    finally:
        if client.is_connected():
            info = status(False)
            try:
                info.wait_for_publish(timeout=2)
            except (RuntimeError, ValueError):
                LOG.warning("Không xác nhận được status đóng")
        client.disconnect()
        client.loop_stop()

if __name__ == "__main__":
    main()
