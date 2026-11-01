"""MQTT 3.1.1; callback chỉ xếp lệnh, luồng chính xử lý."""
import json
import logging
import queue
import threading
from collections import deque
from typing import Any
from .schemas import validate_payload

LOG = logging.getLogger(__name__)


class MqttPublisher:
    def __init__(self, bus_id: str, settings: dict[str, Any], enabled: bool = True) -> None:
        self.bus_id, self.enabled = bus_id, enabled
        self.prefix = f'smartbus/{bus_id}/'
        self.commands: queue.Queue[bytes] = queue.Queue(maxsize=64)
        self.seen: deque[str] = deque(maxlen=32)
        self._lock = threading.Lock()
        self._status: dict[str, Any] | None = None
        self._connected = threading.Event()
        self._frame_info: Any = None
        self.client: Any = None
        if enabled:
            import paho.mqtt.client as mqtt
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                      client_id=f'laptop-{bus_id}', protocol=mqtt.MQTTv311)
            self.client.username_pw_set(settings['username'], settings['password'])
            if settings['tls']:
                self.client.tls_set()
            self.client.will_set(self.prefix + 'vision/status', json.dumps(
                dict(bus_id=bus_id, node='vision', online=False)), qos=1, retain=True)
            self.client.reconnect_delay_set(1, 30)
            self.client.max_queued_messages_set(64)
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_message = self._on_message
        self.settings = settings

    @property
    def connected(self) -> bool:
        return self._connected.is_set()

    def start(self) -> None:
        if self.client:
            self.client.connect_async(self.settings['host'], self.settings['port'], keepalive=30)
            self.client.loop_start()

    def _on_connect(self, client: Any, userdata: Any, flags: Any, reason_code: Any, properties: Any) -> None:
        if reason_code != 0:
            LOG.warning('MQTT từ chối kết nối: %s', reason_code)
            return
        self._connected.set()
        client.subscribe(self.prefix + 'cmd/vision', qos=1)
        with self._lock:
            status = dict(self._status) if self._status else None
        if status:
            from .schemas import now_ms
            status.update(ts=now_ms(), online=True)
            self.publish_status(status)

    def _on_disconnect(self, client: Any, userdata: Any, flags: Any, reason_code: Any, properties: Any) -> None:
        self._connected.clear()
        self._frame_info = None

    def _on_message(self, client: Any, userdata: Any, message: Any) -> None:
        if message.topic != self.prefix + 'cmd/vision' or message.retain:
            return
        try:
            if len(message.payload) > 16384:
                raise ValueError('Lệnh quá lớn')
            self.commands.put_nowait(message.payload)
        except (queue.Full, ValueError) as exc:
            LOG.warning('Bỏ lệnh: %s', exc)

    def publish(self, topic: str, payload: dict[str, Any]) -> bool:
        validate_payload(topic, payload)
        if not self.enabled:
            LOG.info('%s %s', topic, json.dumps(payload, ensure_ascii=False))
            return True
        if not self.connected:
            return False
        qos = 1 if topic in ('vision/status', 'cmd/ack') else 0
        result = self.client.publish(self.prefix + topic, json.dumps(payload, allow_nan=False),
                                     qos=qos, retain=topic == 'vision/status')
        return result.rc == 0

    def publish_frame(self, frame: bytes) -> bool:
        # Chỉ một khung đang gửi; không tích luỹ video khi mạng chậm.
        if not self.connected or not self.client:
            return False
        if self._frame_info is not None:
            try:
                if not self._frame_info.is_published():
                    return False
            except (ValueError, RuntimeError):
                self._frame_info = None
        self._frame_info = self.client.publish(self.prefix + 'vision/frame', frame, qos=0, retain=False)
        return self._frame_info.rc == 0

    def publish_count(self, payload: dict[str, Any]) -> bool:
        return self.publish('vision/count', payload)

    def publish_status(self, payload: dict[str, Any]) -> bool:
        with self._lock:
            self._status = payload.copy()
        return self.publish('vision/status', payload)

    def close(self, status: dict[str, Any]) -> None:
        try:
            validate_payload('vision/status', status)
            if self.client and self.connected:
                info = self.client.publish(self.prefix + 'vision/status', json.dumps(status), qos=1, retain=True)
                info.wait_for_publish(timeout=2)
        finally:
            if self.client:
                self.client.disconnect()
                self.client.loop_stop()
            self._connected.clear()
