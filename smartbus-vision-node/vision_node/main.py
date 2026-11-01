"""Điều phối camera, suy luận, lệnh và kết thúc dịch vụ."""
import argparse
import json
import logging
import queue
import signal
import threading
import time
from pathlib import Path
from typing import Any
from .camera import CameraSource
from .config import ROOT, load_config
from .counter import StableCounter, DirectionalCounter
from .detector import BaseDetector, YoloV8Detector, filter_roi
from .mqtt_publisher import MqttPublisher
from .schemas import build_payload, parse_command
from .streamer import Streamer
from .utils.logger import configure_console, setup_logging

LOG = logging.getLogger(__name__)


class VisionPipeline:
    def __init__(self, config: dict[str, Any], camera: Any, detector: BaseDetector, publisher: Any) -> None:
        self.config, self.camera, self.detector, self.publisher = config, camera, detector, publisher
        self.directional = 'crossing' in config
        self.counter = DirectionalCounter(**config['crossing']) if self.directional else StableCounter(**config['counter'])
        self.stream = None
        self.streamer = Streamer(**config['stream'])
        self.detections: list[Any] = []
        self.video_stop = threading.Event()
        self.video_thread: threading.Thread | None = None
        self.paused = False
        self.person_count = self.counter.value
        self.video_state = ([], self.person_count, self.counter.overlay() if self.directional else None)
        self.frame_id = 0
        self.fps = 0.
        self.last_count = float('-inf')
        self.last_status = float('-inf')
        self.last_infer = float('-inf')
        self.last_log = float('-inf')
        self.status_key: tuple[bool, bool, bool] | None = None
        self.model_name = Path(config['model']['path']).stem
        self.was_camera_ok = False
        self.command_acks: dict[str, dict[str, Any]] = {}

    def status(self, online: bool = True) -> dict[str, Any]:
        return build_payload('vision/status', self.config['bus_id'], online=online,
                             camera_ok=bool(self.camera.camera_ok), fps=self.fps,
                             model=self.model_name, paused=self.paused, streaming=self.streamer.is_active())

    def start_video(self) -> None:
        self.video_thread = threading.Thread(target=self.video_loop, name='video', daemon=True)
        self.video_thread.start()

    def video_loop(self) -> None:
        sequence = -1
        active = False
        while not self.video_stop.wait(.01):
            current = self.streamer.is_active()
            if current != active:
                active = current
                self.publisher.publish_status(self.status())
            if self.paused or not self.camera.camera_ok or not self.streamer.due():
                continue
            latest, frame = self.camera.latest()
            if frame is None or latest == sequence:
                continue
            sequence = latest
            try:
                detections, count, crossing = self.video_state
                raw = self.streamer.encode(frame, detections, count, crossing)
                if self.streamer.is_active() and not self.paused and self.camera.camera_ok:
                    self.publisher.publish_frame(raw)
            except Exception:
                LOG.exception('Không mã hoá/gửi được khung video')

    def close_video(self) -> None:
        self.streamer.stop()
        self.video_stop.set()
        if self.video_thread:
            self.video_thread.join(timeout=5)

    def process_commands(self, now: float) -> None:
        for _ in range(32):
            try:
                data = self.publisher.commands.get_nowait()
            except queue.Empty:
                return
            cmd_id = None
            try:
                try:
                    decoded = json.loads(data) if isinstance(data, (str, bytes)) else data
                    cmd_id = decoded.get('cmd_id') if isinstance(decoded, dict) else None
                except (ValueError, UnicodeError):
                    pass
                if not isinstance(cmd_id, str) or not cmd_id.strip():
                    LOG.warning('Bỏ lệnh không có cmd_id hợp lệ')
                    continue
                if cmd_id in self.publisher.seen:
                    if cmd_id in self.command_acks:
                        self.publisher.publish('cmd/ack', self.command_acks[cmd_id])
                    continue
                self.publisher.seen.append(cmd_id)
                command = parse_command(data)
                action = command['action']
                if action == 'STREAM_START':
                    if self.paused:
                        raise ValueError('Camera đang tạm dừng')
                    self.streamer.start(command['params'].get('fps'))
                elif action == 'STREAM_STOP':
                    self.streamer.stop()
                else:
                    self.paused = action == 'PAUSE'
                    if self.paused:
                        self.streamer.stop()
                    self.detections = []
                    self.counter.clear_tracks() if self.directional else self.counter.reset()
                    self.person_count = self.counter.value
                    self.video_state = ([], self.person_count, self.counter.overlay() if self.directional else None)
                    self.last_count = float('-inf')
                    self.last_infer = float('-inf')
                self.publisher.publish_status(self.status())
                ok, detail = True, f'{action} accepted'
            except Exception as exc:
                ok, detail = False, str(exc)
                LOG.warning('Lệnh lỗi: %s', detail)
            ack = build_payload('cmd/ack', self.config['bus_id'], cmd_id=cmd_id,
                                ok=ok, detail=detail or 'Lệnh thất bại')
            self.command_acks[cmd_id] = ack
            while len(self.command_acks) > 32:
                del self.command_acks[next(iter(self.command_acks))]
            self.publisher.publish('cmd/ack', ack)

    def tick(self, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        camera_ok = bool(self.camera.camera_ok)
        if not camera_ok and self.was_camera_ok:
            self.counter.clear_tracks() if self.directional else self.counter.reset()
            self.detections = []
            self.person_count = self.counter.value
            self.video_state = ([], self.person_count, self.counter.overlay() if self.directional else None)
            self.fps = 0.
        self.was_camera_ok = camera_ok
        ok, frame = self.camera.read()
        self.process_commands(now)
        if self.stream and (not camera_ok or self.paused):
            self.stream.clear()
        processed = False
        if ok and camera_ok and not self.paused and now - self.last_infer >= 1 / self.config['infer_fps']:
            started = time.monotonic()
            try:
                detections = filter_roi(self.detector.detect(frame), frame, self.config['roi'])
                self.detections = detections
                previous = self.person_count
                self.person_count = self.counter.update(detections, frame) if self.directional else self.counter.update(len(detections))
                self.video_state = (detections, self.person_count, self.counter.overlay() if self.directional else None)
                self.frame_id += 1
                elapsed = now - self.last_infer
                self.fps = min(1 / max(time.monotonic() - started, 1e-9), 1 / elapsed) if elapsed != float('inf') else 0.
                self.last_infer = now
                processed = True
                if self.person_count != previous or now - self.last_count >= self.config['publish']['count_interval_s']:
                    payload = build_payload('vision/count', self.config['bus_id'],
                        person_count=self.person_count, raw_count=len(detections),
                        confidence_avg=sum(d.confidence for d in detections) / len(detections) if detections else None,
                        fps=self.fps, frame_id=self.frame_id, model=self.model_name)
                    if self.publisher.publish_count(payload):
                        self.last_count = now
                if self.config['preview'] or self.stream:
                    canvas = self.annotate(frame, detections)
                    if self.stream:
                        self.stream.publish(canvas)
                    if self.config['preview']:
                        import cv2
                        cv2.imshow('Smartbus vision', canvas)
            except Exception:
                LOG.exception('Suy luận lỗi; thử lại ở chu kỳ sau')
                self.last_infer = now
        key = (camera_ok, self.paused, self.streamer.is_active())
        if key != self.status_key or now - self.last_status >= self.config['publish']['status_interval_s']:
            self.publisher.publish_status(self.status())
            self.status_key = key
            self.last_status = now
        if now - self.last_log >= 10:
            LOG.info('fps=%.2f count=%s camera=%s mqtt=%s paused=%s', self.fps,
                     self.person_count, camera_ok, self.publisher.connected, self.paused)
            self.last_log = now
        return processed

    def annotate(self, frame: Any, detections: list[Any]) -> Any:
        import cv2
        import numpy as np
        # Preview, MJPEG nội bộ và video MQTT đều dùng cùng vạch/hướng/sĩ số.
        _, count, crossing = self.video_state
        image = self.streamer.render(frame, detections, count, crossing)
        return cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)



def main() -> None:
    configure_console()
    parser = argparse.ArgumentParser(description='Node camera đếm người Smartbus')
    parser.add_argument('--source')
    parser.add_argument('--bus-id')
    parser.add_argument('--config', default=str(ROOT / 'config/config.yaml'))
    parser.add_argument('--no-mqtt', action='store_true')
    parser.add_argument('--preview', action='store_true', default=None)
    parser.add_argument('--max-frames', type=int)
    parser.add_argument('--mjpeg', action='store_true', help='Enable LAN MJPEG stream')
    parser.add_argument('--mjpeg-host', default='127.0.0.1')
    parser.add_argument('--mjpeg-port', type=int, default=8081)
    args = parser.parse_args()
    if args.max_frames is not None and args.max_frames < 1:
        parser.error('--max-frames phải lớn hơn 0')
    try:
        config = load_config(args.config, dict(source=args.source, bus_id=args.bus_id, preview=args.preview))
    except ValueError as exc:
        parser.error(str(exc))
    setup_logging(config['log_level'], str(ROOT / 'logs'))
    stop = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stop.set())
    model = config['model']
    model_path = Path(model['path'])
    if not model_path.is_absolute():
        model_path = ROOT / model_path
    detector = YoloV8Detector(str(model_path), model['conf'], model['iou'], model['imgsz'], model['device'])
    camera = CameraSource(config['source'], config['frame_width'], config['frame_height'], config['loop_video'])
    publisher = MqttPublisher(config['bus_id'], config['mqtt'], enabled=not args.no_mqtt)
    pipeline = VisionPipeline(config, camera, detector, publisher)
    try:
        if args.mjpeg:
            from .mjpeg import MjpegServer
            pipeline.stream = MjpegServer(args.mjpeg_host, args.mjpeg_port)
            pipeline.stream.start()
            LOG.info('MJPEG listening on %s:%s/stream.mjpg', args.mjpeg_host, args.mjpeg_port)
        publisher.publish_status(pipeline.status())
        publisher.start()
        camera.start()
        pipeline.start_video()
        while not stop.is_set():
            pipeline.tick()
            if config['preview']:
                import cv2
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
            if args.max_frames and pipeline.frame_id >= args.max_frames:
                break
            if camera.ended:
                break
            stop.wait(.01)
    finally:
        try:
            pipeline.close_video()
            publisher.close(pipeline.status(online=False))
        finally:
            if pipeline.stream:
                pipeline.stream.close()
            camera.close()
            if config['preview']:
                import cv2
                cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
