"""Một luồng MQTT mỗi xe; mỗi người xem chỉ giữ khung mới nhất trong RAM."""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from app.services.audit_service import write_audit

logger = logging.getLogger(__name__)


def mjpeg_part(frame: bytes) -> bytes:
    return (b'--frame\r\nContent-Type: image/jpeg\r\nContent-Length: ' +
            str(len(frame)).encode('ascii') + b'\r\n\r\n' + frame + b'\r\n')


@dataclass
class Viewer:
    actor: str
    id: str = field(default_factory=lambda: str(uuid4()))
    queue: asyncio.Queue[bytes] = field(default_factory=lambda: asyncio.Queue(maxsize=1))


class VideoService:
    def __init__(self, commands: Any, db: Any, settings: Any, ws: Any) -> None:
        self.commands, self.db, self.settings, self.ws = commands, db, settings, ws
        self.viewers: dict[str, dict[str, Viewer]] = {}
        self.tasks: dict[str, asyncio.Task] = {}
        self.empty_since: dict[str, float] = {}
        self.frame_at: dict[str, float] = {}
        self.lock = asyncio.Lock()

    async def add(self, bus_id: str, actor: str) -> Viewer:
        async with self.lock:
            viewers = self.viewers.setdefault(bus_id, {})
            if len(viewers) >= self.settings.video_max_viewers:
                raise HTTPException(429, 'Xe đã đạt số người xem tối đa')
            viewer = Viewer(actor)
            await write_audit(self.db, actor, 'VIDEO_VIEW_START', {'bus_id': bus_id, 'viewer_id': viewer.id})
            first = not viewers
            viewers[viewer.id] = viewer
            self.empty_since.pop(bus_id, None)
            if first:
                self.commands.send_video(bus_id, 'STREAM_START')
            if bus_id not in self.tasks:
                self.tasks[bus_id] = asyncio.create_task(self.maintain(bus_id))
            return viewer

    async def remove(self, bus_id: str, viewer: Viewer) -> None:
        async with self.lock:
            viewers = self.viewers.get(bus_id, {})
            if viewers.pop(viewer.id, None) is None:
                return
            if not viewers:
                self.empty_since[bus_id] = time.monotonic()
        # Dọn RAM trước khi ghi Audit, kể cả khi cơ sở dữ liệu bị lỗi.
        try:
            await write_audit(self.db, viewer.actor, 'VIDEO_VIEW_STOP', {'bus_id': bus_id, 'viewer_id': viewer.id})
        except Exception:
            logger.exception('Không ghi được Audit khi đóng video')

    async def maintain(self, bus_id: str) -> None:
        renewed = time.monotonic()
        try:
            while True:
                await asyncio.sleep(min(.25, self.settings.video_renew_s, self.settings.video_stop_grace_s))
                async with self.lock:
                    now = time.monotonic()
                    if self.viewers.get(bus_id):
                        if now - renewed >= self.settings.video_renew_s:
                            self.commands.send_video(bus_id, 'STREAM_START')
                            renewed = now
                    elif now - self.empty_since.get(bus_id, now) >= self.settings.video_stop_grace_s:
                        self.commands.send_video(bus_id, 'STREAM_STOP')
                        self.viewers.pop(bus_id, None)
                        self.empty_since.pop(bus_id, None)
                        self.frame_at.pop(bus_id, None)
                        self.tasks.pop(bus_id, None)
                        return
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception('Lỗi gia hạn video xe %s', bus_id)
            self.tasks.pop(bus_id, None)

    async def frame(self, bus_id: str, payload: bytes) -> None:
        viewers = self.viewers.get(bus_id, {})
        if not viewers or len(payload) > 100000 or not payload.startswith(b'\xff\xd8') or not payload.endswith(b'\xff\xd9'):
            return
        for viewer in list(viewers.values()):
            if viewer.queue.full():
                viewer.queue.get_nowait()
            viewer.queue.put_nowait(payload)
        now = time.monotonic()
        if now - self.frame_at.get(bus_id, float('-inf')) >= 1:
            self.frame_at[bus_id] = now
            # Chỉ gửi nhịp tín hiệu, không gửi ảnh qua WebSocket.
            await self.ws.broadcast('video_frame', bus_id, {})

    async def close(self) -> None:
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for bus_id in list(self.viewers):
            self.commands.send_video(bus_id, 'STREAM_STOP')
            for viewer in list(self.viewers[bus_id].values()):
                await self.remove(bus_id, viewer)
        self.tasks.clear()
        self.viewers.clear()
        self.empty_since.clear()
        self.frame_at.clear()
