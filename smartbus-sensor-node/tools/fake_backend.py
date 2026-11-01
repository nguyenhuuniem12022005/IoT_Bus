"""Gửi một lệnh cảm biến, chờ đúng ack; có thể lặp cmd_id để thử khử trùng."""
from __future__ import annotations
import argparse
import json
import time
import uuid
from typing import Any
import paho.mqtt.client as mqtt
from mqtt_monitor import LOG, configure, make_client, start, stop_event

def main() -> None:
    """Trả mã lỗi khi hết thời gian chờ hoặc node từ chối lệnh."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action", required=True)
    parser.add_argument("--duration", type=int, default=300)
    parser.add_argument("--cmd-id", default=str(uuid.uuid4()))
    parser.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args()
    settings = configure()
    client = make_client("backend", settings)
    stop = stop_event()
    result: list[bool] = []
    sent = False
    prefix = f"smartbus/{settings[5]}/"
    def connected(c: mqtt.Client, userdata: Any, flags: Any, reason: Any, properties: Any) -> None:
        if not reason.is_failure:
            c.subscribe(prefix + "cmd/ack", 1)
    def subscribed(c: mqtt.Client, userdata: Any, mid: int, reasons: Any, properties: Any) -> None:
        nonlocal sent
        if sent or any(reason.is_failure for reason in reasons):
            return
        payload = {"cmd_id": args.cmd_id, "ts": time.time_ns() // 1_000_000,
                   "action": args.action, "params": {"duration_s": args.duration} if args.action == "FAN_ON" else {},
                   "issued_by": "fake_backend"}
        info = c.publish(prefix + "cmd/sensor", json.dumps(payload), qos=1, retain=False)
        sent = info.rc == mqtt.MQTT_ERR_SUCCESS
        LOG.info("Gửi cmd_id=%s action=%s", args.cmd_id, args.action)
    def received(c: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage) -> None:
        try:
            value = json.loads(message.payload)
            if not isinstance(value, dict):
                raise ValueError("Cần object")
            if value.get("cmd_id") == args.cmd_id and value.get("node") == "sensor" and value.get("bus_id") == settings[5]:
                LOG.info("ACK %s", json.dumps(value, ensure_ascii=False))
                result.append(value.get("ok") is True)
                stop.set()
        except (ValueError, UnicodeError):
            LOG.warning("Ack sai định dạng")
    client.on_connect = connected
    client.on_subscribe = subscribed
    client.on_message = received
    start(client, settings)
    deadline = time.monotonic() + args.timeout
    try:
        while not stop.wait(0.1) and time.monotonic() < deadline:
            pass
    finally:
        client.disconnect()
        client.loop_stop()
    if not result:
        LOG.error("TIMEOUT: không có ack (lệnh trùng cmd_id sẽ không được ack)")
    raise SystemExit(0 if result and result[0] else 1)

if __name__ == "__main__":
    main()
