import asyncio
import json
import logging
import threading
from typing import Any

import paho.mqtt.client as mqtt

from app.config import Settings
from app.mqtt_bridge.handlers import MessageHandler

logger = logging.getLogger(__name__)


class MQTTBridge:
    def __init__(self, settings: Settings, handler: MessageHandler, loop: asyncio.AbstractEventLoop) -> None:
        self.settings, self.handler, self.loop = settings, handler, loop
        self.connected = False
        self.stopping = False
        self.pending: set[Any] = set()
        self.guard = threading.Lock()
        self.video_pending: dict[str, bytes] = {}
        self.video_scheduled: set[str] = set()
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=settings.mqtt_client_id,
                                  protocol=mqtt.MQTTv311, reconnect_on_failure=True)
        self.client.username_pw_set(settings.mqtt_username, settings.mqtt_password)
        if settings.mqtt_tls:
            self.client.tls_set()
        self.client.reconnect_delay_set(min_delay=1, max_delay=60)
        self.client.max_queued_messages_set(100)
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message

    def on_connect(self, client: mqtt.Client, userdata: Any, flags: Any, reason_code: Any, properties: Any) -> None:
        self.connected = not reason_code.is_failure
        if self.connected:
            client.subscribe("smartbus/+/#", qos=1)
        else:
            logger.warning("MQTT connection refused")

    def on_disconnect(self, client: mqtt.Client, userdata: Any, flags: Any, reason_code: Any, properties: Any) -> None:
        self.connected = False

    def on_message(self, client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage) -> None:
        if self.stopping or len(message.payload) > 100000:
            return
        if message.topic.endswith('/vision/frame'):
            # Gộp ngay ở luồng MQTT để callback video không lấp hàng đợi count.
            with self.guard:
                if message.topic not in self.video_scheduled and len(self.video_scheduled) >= 100:
                    return
                self.video_pending[message.topic] = bytes(message.payload)
                if message.topic in self.video_scheduled:
                    return
                self.video_scheduled.add(message.topic)
            future = asyncio.run_coroutine_threadsafe(self.drain_video(message.topic), self.loop)
            with self.guard:
                self.pending.add(future)
            future.add_done_callback(self.completed)
            return
        with self.guard:
            if len(self.pending) >= 1000:
                logger.warning("MQTT processing capacity exceeded")
                return
        future = asyncio.run_coroutine_threadsafe(self.handler.handle(message.topic, message.payload), self.loop)
        with self.guard:
            self.pending.add(future)
        future.add_done_callback(self.completed)

    async def drain_video(self, topic: str) -> None:
        try:
            while not self.stopping:
                with self.guard:
                    payload = self.video_pending.pop(topic, None)
                    if payload is None:
                        self.video_scheduled.discard(topic)
                        return
                await self.handler.handle(topic, payload)
                await asyncio.sleep(0)
            with self.guard:
                self.video_scheduled.discard(topic)
                self.video_pending.pop(topic, None)
        except BaseException:
            with self.guard:
                self.video_scheduled.discard(topic)
                self.video_pending.pop(topic, None)
            raise

    def completed(self, future: Any) -> None:
        with self.guard:
            self.pending.discard(future)

    def publish(self, topic: str, payload: dict[str, Any]) -> bool:
        if not self.connected:
            return False
        result = self.client.publish(topic, json.dumps(payload), qos=1, retain=False)
        return result.rc == mqtt.MQTT_ERR_SUCCESS

    def start(self) -> None:
        self.client.connect_async(self.settings.mqtt_host, self.settings.mqtt_port, keepalive=30)
        self.client.loop_start()

    async def stop(self) -> None:
        self.stopping = True
        self.client.disconnect()
        await asyncio.to_thread(self.client.loop_stop)
        with self.guard:
            pending = list(self.pending)
        if pending:
            await asyncio.gather(*(asyncio.wrap_future(f) for f in pending), return_exceptions=True)
