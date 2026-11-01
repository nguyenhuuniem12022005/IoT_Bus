"""Đối chiếu chính xác trường và kiểu dữ liệu của hợp đồng."""
import json
import pytest
from vision_node.schemas import FIELDS, build_payload, parse_command, validate_payload


def test_payload_contract() -> None:
    payloads = {
        'vision/count': dict(person_count=2, raw_count=3, confidence_avg=.71, fps=4.8, frame_id=1234, model='yolov8n'),
        'vision/status': dict(online=True, camera_ok=True, fps=4.8, model='yolov8n', paused=False, streaming=False),
        'cmd/ack': dict(cmd_id='abc', ok=True, detail='PAUSE accepted'),
    }
    for topic, values in payloads.items():
        payload = build_payload(topic, 'bus01', **values)
        assert set(payload) == FIELDS[topic]
        assert type(payload['ts']) is int and payload['ts'] > 0
        assert json.loads(json.dumps(payload)) == payload
        with pytest.raises(ValueError):
            validate_payload(topic, dict(payload, extra=1))
        for key in payload:
            with pytest.raises(ValueError):
                validate_payload(topic, {k: v for k, v in payload.items() if k != key})


@pytest.mark.parametrize('key,value', [('person_count', True), ('raw_count', -1), ('fps', float('nan')),
    ('confidence_avg', 1.1), ('confidence_avg', None), ('frame_id', 1.2), ('node', 'sensor'), ('ts', True)])
def test_count_bad_types(key: str, value: object) -> None:
    payload = build_payload('vision/count', 'bus01', person_count=1, raw_count=1,
                            confidence_avg=.8, fps=5., frame_id=1, model='yolov8n')
    payload[key] = value
    with pytest.raises(ValueError):
        validate_payload('vision/count', payload)


@pytest.mark.parametrize('action', ['STREAM_START', 'STREAM_STOP', 'PAUSE', 'RESUME'])
def test_parse_command(action: str) -> None:
    data = dict(cmd_id='id', ts=1, action=action, params={}, issued_by='operator')
    assert parse_command(json.dumps(data).encode()) == data


@pytest.mark.parametrize('change', [dict(action='FAN_ON'), dict(params=[]), dict(params={'x': 1}),
    dict(ts=True), dict(ts=-1), dict(cmd_id=''), dict(issued_by=''), dict(action=[])])
def test_invalid_command(change: dict) -> None:
    data = dict(cmd_id='id', ts=1, action='PAUSE', params={}, issued_by='operator')
    with pytest.raises(ValueError):
        parse_command(dict(data, **change))


@pytest.mark.parametrize('data', [b'\xff', 'no json', '[]', '{}'])
def test_malformed_command(data: str | bytes) -> None:
    with pytest.raises(ValueError):
        parse_command(data)
