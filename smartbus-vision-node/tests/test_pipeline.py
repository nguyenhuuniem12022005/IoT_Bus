"""Kiểm tra luồng độc lập, lệnh, phục hồi và adapter phần cứng giả."""
import json
import time
from types import SimpleNamespace
from typing import Any
import pytest
from vision_node.detector import Detection, FakeDetector, filter_roi, point_in_polygon
from vision_node.main import VisionPipeline
from vision_node.mqtt_publisher import MqttPublisher


def command(action: str, cmd_id: str = 'id') -> bytes:
    return json.dumps(dict(cmd_id=cmd_id, ts=1, action=action, params={}, issued_by='test')).encode()


def messages(publisher: Any, topic: str) -> list[dict]:
    return [payload for actual, payload in publisher.messages if actual == topic]


def test_independent_pipeline_and_intervals(config: dict, camera: Any, publisher: Any) -> None:
    pipeline = VisionPipeline(config, camera, FakeDetector([0] * 6 + [2] * 10), publisher)
    for index in range(16):
        pipeline.tick(index * .25)
    counts = messages(publisher, 'vision/count')
    assert counts[0]['person_count'] == 0 and counts[-1]['person_count'] == 2
    assert len(counts) >= 4
    assert pipeline.frame_id == 16


def test_pause_resume_stream_invalid_duplicate(config: dict, camera: Any, publisher: Any) -> None:
    pipeline = VisionPipeline(config, camera, FakeDetector([2]), publisher)
    pipeline.tick(0)
    publisher.commands.put(command('PAUSE', 'pause'))
    pipeline.tick(.25)
    assert pipeline.paused and pipeline.frame_id == 1
    pipeline.tick(5)
    assert pipeline.frame_id == 1
    assert messages(publisher, 'vision/status')[-1]['paused']
    pipeline.tick(5.1)
    publisher.commands.put(command('RESUME', 'resume'))
    publisher.commands.put(command('RESUME', 'resume'))
    publisher.commands.put(command('INVALID', 'bad'))
    publisher.commands.put(b'broken json')
    publisher.commands.put(b'{"cmd_id":"malformed"}')
    pipeline.tick(5.5)
    assert not pipeline.paused and pipeline.frame_id == 2
    acks = messages(publisher, 'cmd/ack')
    assert len([ack for ack in acks if ack['cmd_id'] == 'resume']) == 2
    assert [ack['ok'] for ack in acks if ack['cmd_id'] in ('bad', 'malformed')] == [False, False]


def test_camera_loss_and_mqtt_recovery(config: dict, camera: Any, publisher: Any) -> None:
    pipeline = VisionPipeline(config, camera, FakeDetector([2]), publisher)
    pipeline.tick(0)
    camera.camera_ok = False
    pipeline.tick(3)
    assert not messages(publisher, 'vision/status')[-1]['camera_ok']
    count_length = len(messages(publisher, 'vision/count'))
    publisher.commands.put(command('INVALID'))
    pipeline.tick(4)
    assert not messages(publisher, 'cmd/ack')[-1]['ok']
    assert len(messages(publisher, 'vision/count')) == count_length
    camera.camera_ok = True
    publisher.connected = False
    pipeline.tick(5)
    pipeline.tick(6)
    assert pipeline.frame_id == 3
    publisher.connected = True
    pipeline.tick(7)
    assert messages(publisher, 'vision/count')[-1]['frame_id'] == 4
    assert len(messages(publisher, 'vision/count')) == count_length + 1


def test_roi(camera: Any) -> None:
    roi = [[.1, .1], [.9, .1], [.9, .9], [.1, .9]]
    inside = Detection((100., 100., 200., 200.), .9)
    outside = Detection((0., 0., 10., 10.), .8)
    assert filter_roi([inside, outside], camera.frame, roi) == [inside]
    assert filter_roi([inside, outside], camera.frame, []) == [inside, outside]
    assert point_in_polygon(.1, .5, roi)


def test_mqtt_contract_and_no_offline_buffer(config: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    import paho.mqtt.client as mqtt

    class FakeClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.kwargs = kwargs
            self.calls: list[tuple] = []

        def username_pw_set(self, *args: Any) -> None:
            pass

        def will_set(self, *args: Any, **kwargs: Any) -> None:
            self.will = (args, kwargs)

        def reconnect_delay_set(self, *args: Any) -> None:
            self.delay = args

        def max_queued_messages_set(self, value: int) -> None:
            pass

        def subscribe(self, topic: str, qos: int) -> None:
            self.calls.append(('subscribe', topic, qos))

        def publish(self, *args: Any, **kwargs: Any) -> Any:
            self.calls.append(('publish', args, kwargs))
            return SimpleNamespace(rc=0)

    monkeypatch.setattr(mqtt, 'Client', FakeClient)
    publisher = MqttPublisher('bus01', config['mqtt'])
    client = publisher.client
    assert client.kwargs['client_id'] == 'laptop-bus01'
    assert client.delay == (1, 30)
    assert client.will[1] == dict(qos=1, retain=True)
    assert json.loads(client.will[0][1]) == dict(bus_id='bus01', node='vision', online=False)
    from vision_node.schemas import build_payload
    count = build_payload('vision/count', 'bus01', person_count=0, raw_count=0,
                           confidence_avg=None, fps=5., frame_id=1, model='yolov8n')
    assert not publisher.publish_count(count) and not client.calls
    publisher._on_connect(client, None, None, 0, None)
    assert client.calls == [('subscribe', 'smartbus/bus01/cmd/vision', 1)]
    assert publisher.publish_count(count)
    assert client.calls[-1][2] == dict(qos=0, retain=False)
    publisher._on_disconnect(client, None, None, 1, None)
    assert not publisher.publish_count(count)
    publisher._on_message(client, None, SimpleNamespace(topic='smartbus/bus01/cmd/vision', retain=False, payload=command('PAUSE')))
    assert publisher.commands.get_nowait() == command('PAUSE')
    publisher._on_message(client, None, SimpleNamespace(topic='smartbus/bus01/sensor/telemetry', retain=False, payload=b'{}'))
    assert publisher.commands.empty()


def test_camera_reopens_after_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    from vision_node.camera import CameraSource
    import numpy as np
    camera = CameraSource(0)
    captures: list[Any] = []

    class Capture:
        def __init__(self, opened: bool) -> None:
            self.opened, self.released = opened, False

        def isOpened(self) -> bool:
            return self.opened

        def get(self, key: int) -> float:
            return 5.

        def read(self) -> tuple[bool, Any]:
            return True, np.zeros((24, 32, 3), dtype=np.uint8)

        def release(self) -> None:
            self.released = True

    def fake_open() -> Capture:
        capture = Capture(bool(captures))
        captures.append(capture)
        return capture

    monkeypatch.setattr(camera, '_open', fake_open)
    camera.start()
    deadline = time.monotonic() + 3
    try:
        while not camera.camera_ok and time.monotonic() < deadline:
            time.sleep(.02)
        assert camera.camera_ok and len(captures) == 2
        assert camera.read()[0]
    finally:
        camera.close()
    assert all(capture.released for capture in captures)


def test_yolo_loaded_once_and_person_only(monkeypatch: pytest.MonkeyPatch, camera: Any) -> None:
    import sys
    from vision_node.detector import YoloV8Detector
    calls: list[dict] = []
    loaded: list[str] = []

    class Tensor:
        def __init__(self, value: list) -> None:
            self.value = value

        def cpu(self) -> 'Tensor':
            return self

        def tolist(self) -> list:
            return self.value

    class Model:
        def __init__(self, path: str) -> None:
            loaded.append(path)

        def predict(self, frame: Any, **options: Any) -> list:
            calls.append(options)
            return [SimpleNamespace(boxes=SimpleNamespace(
                xyxy=Tensor([[1, 2, 3, 4]]), conf=Tensor([.8])))]

    monkeypatch.setitem(sys.modules, 'ultralytics', SimpleNamespace(YOLO=Model))
    monkeypatch.setitem(sys.modules, 'torch', SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False)))
    detector = YoloV8Detector('models/yolov8n.pt')
    assert detector.detect(camera.frame) == [Detection((1., 2., 3., 4.), .8)]
    detector.detect(camera.frame)
    assert len(loaded) == 1 and len(calls) == 3
    assert all(c['classes'] == [0] and c['device'] == 'cpu' and not c['save'] for c in calls)


@pytest.mark.parametrize('arguments', [
    ['-m', 'vision_node.main'], ['scripts/test_camera.py'],
    ['scripts/benchmark_model.py'], ['scripts/mock_subscriber.py']])
def test_cli_help_with_redirected_legacy_console(arguments: list[str]) -> None:
    import os
    import subprocess
    import sys
    from vision_node.config import ROOT
    result = subprocess.run([sys.executable, *arguments, '--help'], cwd=ROOT,
                            env=dict(os.environ, PYTHONIOENCODING='cp1252', PYTHONDONTWRITEBYTECODE='1'),
                            capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr.decode('utf-8', errors='replace')
    assert '--help' in result.stdout.decode('utf-8')


