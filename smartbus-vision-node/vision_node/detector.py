"""Bộ phát hiện người và bộ lọc đa giác ROI."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Detection:
    bbox: tuple[float, float, float, float]
    confidence: float


class BaseDetector(ABC):
    @abstractmethod
    def detect(self, frame: Any) -> list[Detection]:
        """Trả các hộp người trên khung BGR."""


def point_in_polygon(x: float, y: float, polygon: list[list[float]]) -> bool:
    inside = False
    for i, (ax, ay) in enumerate(polygon):
        bx, by = polygon[i - 1]
        cross = (x - ax) * (by - ay) - (y - ay) * (bx - ax)
        if abs(cross) < 1e-9 and min(ax, bx) <= x <= max(ax, bx) and min(ay, by) <= y <= max(ay, by):
            return True
        if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
            inside = not inside
    return inside


def filter_roi(detections: list[Detection], frame: Any, roi: list[list[float]]) -> list[Detection]:
    if not roi:
        return detections
    height, width = frame.shape[:2]
    return [d for d in detections if point_in_polygon(
        (d.bbox[0] + d.bbox[2]) / (2 * width),
        (d.bbox[1] + d.bbox[3]) / (2 * height), roi)]


class YoloV8Detector(BaseDetector):
    def __init__(self, model_path: str, conf: float = .40, iou: float = .50,
                 imgsz: int = 640, device: str = "auto") -> None:
        import numpy as np
        import torch
        from ultralytics import YOLO
        Path(model_path).parent.mkdir(parents=True, exist_ok=True)
        self.model = YOLO(model_path)
        resolved = ("0" if torch.cuda.is_available() else "cpu") if device == "auto" else device.replace("cuda:", "")
        self.options = dict(conf=conf, iou=iou, imgsz=imgsz, device=resolved,
                            classes=[0], verbose=False, save=False, save_txt=False,
                            save_crop=False, visualize=False)
        self.detect(np.zeros((imgsz, imgsz, 3), dtype=np.uint8))

    def detect(self, frame: Any) -> list[Detection]:
        result = self.model.predict(frame, **self.options)[0]
        return [Detection(tuple(map(float, box)), float(conf))
                for box, conf in zip(result.boxes.xyxy.cpu().tolist(), result.boxes.conf.cpu().tolist())]


class FakeDetector(BaseDetector):
    def __init__(self, script: list[int]) -> None:
        if not script or any(type(n) is not int or n < 0 for n in script):
            raise ValueError("Kịch bản cần số đếm không âm")
        self.script = script
        self.index = 0

    def detect(self, frame: Any) -> list[Detection]:
        count = self.script[min(self.index, len(self.script) - 1)]
        self.index += 1
        height, width = frame.shape[:2]
        return [Detection((0., 0., float(width), float(height)), .9) for _ in range(count)]
