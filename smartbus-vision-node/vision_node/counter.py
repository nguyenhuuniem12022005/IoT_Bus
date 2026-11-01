"""Làm mượt số đếm bằng trung vị và xác nhận liên tiếp."""
import logging
import math
from dataclasses import dataclass, field
from typing import Any
from collections import deque
from statistics import median_low


class StableCounter:
    def __init__(self, window: int = 5, min_change_frames: int = 2) -> None:
        if type(window) is not int or window < 1 or type(min_change_frames) is not int or min_change_frames < 1:
            raise ValueError("Cửa sổ và số khung xác nhận phải là số nguyên dương")
        self.window = window
        self.min_change_frames = min_change_frames
        self.reset()

    def reset(self) -> None:
        self.history: deque[int] = deque(maxlen=self.window)
        self.value = 0
        self.candidate = 0
        self.streak = 0

    def update(self, raw_count: int) -> int:
        if type(raw_count) is not int or raw_count < 0:
            raise ValueError("Số người phải là số nguyên không âm")
        self.history.append(raw_count)
        candidate = int(median_low(self.history))
        self.streak = self.streak + 1 if candidate == self.candidate else 1
        self.candidate = candidate
        if self.streak >= self.min_change_frames:
            self.value = candidate
        return self.value


@dataclass
class Track:
    x: float
    y: float
    side: int
    missed: int = 0
    vx: float = 0.
    vy: float = 0.
    trail: deque[tuple[float, float]] = field(default_factory=lambda: deque(maxlen=16))


class DirectionalCounter:
    """Theo dõi tâm người qua hai mép vùng đệm, cộng vào và trừ ra."""
    def __init__(self, direction: str = "up", line: float = .5, margin: float = .04,
                 max_distance: float = .35, max_missed: int = 5, initial_count: int = 0) -> None:
        if direction not in ("up", "down", "left", "right"):
            raise ValueError("Hướng vào phải là up/down/left/right")
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in (line, margin, max_distance)):
            raise ValueError("Toạ độ và khoảng ghép phải hữu hạn")
        if not 0 < margin < min(line, 1-line) or not 0 < max_distance <= 1:
            raise ValueError("Vạch/vùng đệm hoặc khoảng ghép không hợp lệ")
        if any(type(v) is not int or v < 0 for v in (max_missed, initial_count)):
            raise ValueError("Số khung mất dấu và sĩ số đầu phải là số nguyên không âm")
        self.direction, self.line, self.margin = direction, line, margin
        self.max_distance, self.max_missed, self.initial_count = max_distance, max_missed, initial_count
        self.reset()

    def reset(self) -> None:
        self.value = self.initial_count
        self.entered = self.exited = 0
        self.clear_tracks()

    def clear_tracks(self) -> None:
        # Mất camera/tạm dừng chỉ xoá dấu theo dõi, giữ sĩ số đã đếm.
        self.tracks: dict[int, Track] = {}
        self.next_id = 1

    def overlay(self) -> dict[str, Any]:
        # Sao chép dữ liệu để luồng video không đọc dict đang được cập nhật.
        return dict(direction=self.direction, line=self.line, margin=self.margin,
                    entered=self.entered, exited=self.exited,
                    tracks=[dict(id=key, trail=list(track.trail))
                            for key, track in self.tracks.items() if track.missed == 0])

    def update(self, detections: list[Any], frame: Any) -> int:
        h, w = frame.shape[:2]
        points = [((d.bbox[0]+d.bbox[2])/2/w, (d.bbox[1]+d.bbox[3])/2/h) for d in detections]
        pairs = []
        for key, track in self.tracks.items():
            for i, (x, y) in enumerate(points):
                distance = (track.x-x)**2 + (track.y-y)**2
                if distance <= self.max_distance**2:
                    # Dự đoán giúp giữ ID khi hai người đi ngược chiều qua nhau.
                    steps = track.missed + 1
                    cost = (track.x+track.vx*steps-x)**2 + (track.y+track.vy*steps-y)**2
                    pairs.append((cost, key, i))
        used: set[int] = set()
        assigned: dict[int, int] = {}
        for _, key, i in sorted(pairs):
            if key not in used and i not in assigned:
                used.add(key)
                assigned[i] = key
        for key in list(self.tracks):
            if key not in used:
                self.tracks[key].missed += 1
                if self.tracks[key].missed > self.max_missed:
                    del self.tracks[key]
        for i, (x, y) in enumerate(points):
            coordinate = y if self.direction in ("up", "down") else x
            side = -1 if coordinate < self.line-self.margin else 1 if coordinate > self.line+self.margin else 0
            key = assigned.get(i)
            track = self.tracks.get(key)
            if track is None:
                key = self.next_id
                self.next_id += 1
                track = Track(x, y, side)
                self.tracks[key] = track
            else:
                if side and track.side and side != track.side:
                    boarding = side == (-1 if self.direction in ("up", "left") else 1)
                    if boarding:
                        self.entered += 1
                        self.value += 1
                    else:
                        self.exited += 1
                        self.value = max(0, self.value - 1)
                    logging.getLogger(__name__).info('ID=%s %s: vao=%s ra=%s con=%s',
                        key, 'VAO' if boarding else 'RA', self.entered, self.exited, self.value)
                steps = track.missed + 1
                track.vx, track.vy = (x-track.x)/steps, (y-track.y)/steps
                track.x, track.y = x, y
                track.side = side or track.side
                track.missed = 0
            track.trail.append((x, y))
        return self.value
