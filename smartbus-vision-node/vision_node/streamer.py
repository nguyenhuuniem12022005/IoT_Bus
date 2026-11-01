"""Mã hoá video trong RAM, giới hạn tốc độ và thời hạn thuê luồng."""
import io
import math
import threading
import time
from typing import Any, Callable

class Streamer:
    def __init__(self, fps: float = 8, width: int = 480, height: int = 360,
                 jpeg_quality: int = 60, max_kb: int = 80, draw_boxes: bool = True,
                 lease_s: float = 30, clock: Callable[[], float] = time.monotonic) -> None:
        if any(type(v) is not int or v <= 0 for v in (width, height, max_kb)):
            raise ValueError('Kích thước và max_kb phải là số nguyên dương')
        if type(jpeg_quality) is not int or not 30 <= jpeg_quality <= 95:
            raise ValueError('Chất lượng JPEG phải từ 30 đến 95')
        if not math.isfinite(lease_s) or lease_s <= 0 or type(draw_boxes) is not bool:
            raise ValueError('Thời hạn hoặc draw_boxes không hợp lệ')
        self.width, self.height, self.jpeg_quality = width, height, jpeg_quality
        self.max_kb, self.draw_boxes, self.lease_s = max_kb, draw_boxes, lease_s
        self.clock = clock
        self.fps = self.clamp_fps(fps)
        self._deadline = float('-inf')
        self._last_frame = float('-inf')
        self._lock = threading.RLock()
        self._font: Any = None

    @staticmethod
    def clamp_fps(fps: float) -> float:
        if type(fps) not in (float, int) or not math.isfinite(fps):
            raise ValueError('FPS phải là số hữu hạn')
        return max(1., min(15., fps))

    def start(self, fps: float | None = None) -> None:
        with self._lock:
            if fps is not None:
                self.fps = self.clamp_fps(fps)
            self._deadline = self.clock() + self.lease_s

    def stop(self) -> None:
        with self._lock:
            self._deadline = float('-inf')

    def is_active(self) -> bool:
        with self._lock:
            return self.clock() < self._deadline

    def due(self) -> bool:
        with self._lock:
            now = self.clock()
            if not self.is_active() or now - self._last_frame < 1 / self.fps:
                return False
            self._last_frame = now
            return True

    def render(self, frame: Any, detections: list[Any], person_count: int,
               crossing: dict[str, Any] | None = None) -> Any:
        import cv2
        from PIL import Image, ImageDraw, ImageFont
        h, w = frame.shape[:2]
        resized = cv2.resize(frame, (self.width, self.height))
        image = Image.fromarray(cv2.cvtColor(resized, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(image)
        if self.draw_boxes:
            for detection in detections:
                x1, y1, x2, y2 = detection.bbox
                draw.rectangle((x1*self.width/w, y1*self.height/h,
                                x2*self.width/w, y2*self.height/h), outline='#00ff60', width=2)
        # Dùng font hệ thống có dấu tiếng Việt; font mặc định Pillow thiếu các dấu này.
        if self._font is None:
            for name in ('arial.ttf', 'DejaVuSans.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
                         '/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf'):
                try:
                    self._font = ImageFont.truetype(name, 20)
                    break
                except OSError:
                    continue
            if self._font is None:
                raise ValueError('Cần font hệ thống Arial, DejaVu Sans hoặc Liberation Sans để vẽ tiếng Việt')
        if crossing:
            self.draw_crossing(draw, crossing)
            draw.rectangle((0, 0, self.width, 66), fill='#101b29')
            draw.text((10, 6), f'Còn trên xe: {person_count}', font=self._font, fill='#00ff60')
            draw.text((10, 34), f"Vào: {crossing['entered']}  |  Ra: {crossing['exited']}  |  Thấy: {len(detections)}",
                      font=self._font, fill='white')
        else:
            draw.text((10, 10), f'Người: {person_count}', font=self._font,
                      fill='#00ff60', stroke_width=1, stroke_fill='black')
        return image

    def draw_crossing(self, draw: Any, crossing: dict[str, Any]) -> None:
        w, h = self.width, self.height
        vertical = crossing['direction'] in ('left', 'right')
        axis = w if vertical else h
        pos = int(crossing['line'] * axis)
        draw.line((pos, 0, pos, h) if vertical else (0, pos, w, pos), fill='#ffe04b', width=3)
        # Hai đường đứt là mép xác nhận, tránh đếm khi chỉ đứng rung trên vạch.
        for edge in (crossing['line']-crossing['margin'], crossing['line']+crossing['margin']):
            offset = int(edge*axis)
            for step in range(0, h if vertical else w, 16):
                draw.line((offset, step, offset, step+8) if vertical else (step, offset, step+8, offset),
                          fill='#ffe04b', width=1)
        dx, dy = {'left': (-1, 0), 'right': (1, 0), 'up': (0, -1), 'down': (0, 1)}[crossing['direction']]
        length = min(w, h)*.16
        for index, (sign, label, color) in enumerate(((1, 'VÀO +1', '#00ff60'), (-1, 'RA -1', '#ff9b45'))):
            cx, cy = (pos, h*(.38 + index*.32)) if vertical else (w*(.28 + index*.44), pos)
            ax, ay = dx*sign, dy*sign
            start, end = (cx-ax*length, cy-ay*length), (cx+ax*length, cy+ay*length)
            draw.line((*start, *end), fill=color, width=4)
            ex, ey = end
            draw.polygon([(ex, ey), (ex-ax*12-ay*7, ey-ay*12+ax*7),
                          (ex-ax*12+ay*7, ey-ay*12-ax*7)], fill=color)
            draw.text((max(5, cx-45), max(68, cy-length-30)), label, font=self._font,
                      fill=color, stroke_width=1, stroke_fill='black')
        for track in crossing['tracks']:
            points = [(x*w, y*h) for x, y in track['trail']]
            if len(points) > 1:
                draw.line(points, fill='#55dfff', width=2)
            if points:
                x, y = points[-1]
                draw.ellipse((x-4, y-4, x+4, y+4), fill='#55dfff')
                draw.text((x+6, y+4), f"ID {track['id']}", font=self._font,
                          fill='#55dfff', stroke_width=1, stroke_fill='black')

    def encode(self, frame: Any, detections: list[Any], person_count: int,
               crossing: dict[str, Any] | None = None) -> bytes:
        image = self.render(frame, detections, person_count, crossing)
        for quality in range(self.jpeg_quality, 29, -1):
            output = io.BytesIO()
            image.save(output, format='JPEG', quality=quality)
            raw = output.getvalue()
            if len(raw) <= self.max_kb * 1024:
                return raw
        raise ValueError('Khung JPEG vượt max_kb ở chất lượng tối thiểu 30')
