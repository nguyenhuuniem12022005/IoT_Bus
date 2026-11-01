"""Kiểm tra lease, tốc độ và giới hạn RAM mà không cần phần cứng."""
import time
from types import SimpleNamespace
import cv2
import numpy as np
import pytest
from vision_node.streamer import Streamer
from vision_node.main import VisionPipeline
from vision_node.detector import FakeDetector
from vision_node.mqtt_publisher import MqttPublisher
from tests.test_pipeline import command, messages


def test_lease_renew_stop_and_fps() -> None:
    now = [0.]
    stream = Streamer(clock=lambda: now[0])
    assert not stream.is_active()
    stream.start(100)
    assert stream.fps == 15 and stream.due() and not stream.due()
    now[0] = 20
    stream.start(-2)
    assert stream.fps == 1
    now[0] = 49.9
    assert stream.is_active()
    now[0] = 50
    assert not stream.is_active()
    stream.start()
    stream.stop()
    assert not stream.is_active()


def test_encode_size_quality_floor() -> None:
    frame = np.random.default_rng(1).integers(0, 256, (360, 480, 3), dtype=np.uint8)
    stream = Streamer(jpeg_quality=90, max_kb=60)
    raw = stream.encode(frame, [SimpleNamespace(bbox=(10, 20, 100, 200))], 3)
    assert len(raw) <= 60 * 1024
    assert cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR).shape[:2] == (360, 480)
    with pytest.raises(ValueError, match='30'):
        Streamer(max_kb=1).encode(frame, [], 0)


def test_commands_pause_and_status(config, camera, publisher) -> None:
    pipeline = VisionPipeline(config, camera, FakeDetector([1]), publisher)
    publisher.commands.put(command('STREAM_START', 'start'))
    pipeline.tick(0)
    assert pipeline.streamer.is_active()
    assert messages(publisher, 'vision/status')[-1]['streaming']
    publisher.commands.put(command('PAUSE', 'pause'))
    pipeline.tick(1)
    assert not pipeline.streamer.is_active()
    publisher.commands.put(command('STREAM_START', 'paused-start'))
    pipeline.tick(2)
    assert not messages(publisher, 'cmd/ack')[-1]['ok']
    publisher.commands.put(command('RESUME', 'resume'))
    publisher.commands.put(command('STREAM_START', 'restart'))
    publisher.commands.put(command('STREAM_STOP', 'stop'))
    pipeline.tick(3)
    assert not pipeline.streamer.is_active() and not pipeline.paused


def test_frame_publish_drops_inflight(config) -> None:
    publisher = MqttPublisher('bus01', config['mqtt'], enabled=False)
    calls = []
    done = [False]
    def publish(*args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(rc=0, is_published=lambda: done[0])
    publisher.client = SimpleNamespace(publish=publish)
    publisher._connected.set()
    assert publisher.publish_frame(b'jpeg')
    assert not publisher.publish_frame(b'next') and len(calls) == 1
    done[0] = True
    assert publisher.publish_frame(b'new')
    assert calls[-1] == (('smartbus/bus01/vision/frame', b'new'), {'qos': 0, 'retain': False})


def test_video_independent_of_yolo_and_no_old_frame(config, camera, publisher) -> None:
    pipeline = VisionPipeline(config, camera, FakeDetector([0]), publisher)
    sequence = [1]
    camera.latest = lambda: (sequence[0], camera.frame.copy())
    sent = []
    publisher.publish_frame = lambda raw: sent.append(raw)
    pipeline.streamer.start(15)
    pipeline.start_video()
    try:
        deadline = time.monotonic() + 2
        while not sent and time.monotonic() < deadline:
            time.sleep(.01)
        assert len(sent) == 1 and pipeline.frame_id == 0
        time.sleep(.15)
        assert len(sent) == 1
        camera.camera_ok = False
        sequence[0] += 1
        time.sleep(.15)
        assert len(sent) == 1
    finally:
        pipeline.close_video()
