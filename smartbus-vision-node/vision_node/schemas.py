"""Dựng và kiểm tra hợp đồng JSON MQTT một cách nghiêm ngặt."""
import json
import math
import time
from typing import Any

FIELDS = {
    'vision/count': {'ts', 'bus_id', 'node', 'person_count', 'raw_count', 'confidence_avg', 'fps', 'frame_id', 'model'},
    'vision/status': {'ts', 'bus_id', 'node', 'online', 'camera_ok', 'fps', 'model', 'paused', 'streaming'},
    'cmd/ack': {'cmd_id', 'ts', 'bus_id', 'node', 'ok', 'detail'},
}


def now_ms() -> int:
    return time.time_ns() // 1_000_000


def nonnegative_int(value: Any) -> bool:
    return type(value) is int and value >= 0


def number(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def validate_payload(topic: str, payload: dict[str, Any]) -> dict[str, Any]:
    if topic not in FIELDS or set(payload) != FIELDS[topic]:
        raise ValueError("Payload thiếu hoặc thừa trường")
    if not nonnegative_int(payload['ts']) or not isinstance(payload['bus_id'], str) or not payload['bus_id']:
        raise ValueError("ts hoặc bus_id không hợp lệ")
    if payload['node'] != 'vision':
        raise ValueError("node phải là vision")
    for key in ('person_count', 'raw_count', 'frame_id'):
        if key in payload and not nonnegative_int(payload[key]):
            raise ValueError(f"{key} phải là số nguyên không âm")
    for key in ('online', 'camera_ok', 'paused', 'streaming', 'ok'):
        if key in payload and type(payload[key]) is not bool:
            raise ValueError(f"{key} phải là boolean")
    if 'fps' in payload and (not number(payload['fps']) or payload['fps'] < 0):
        raise ValueError("fps không hợp lệ")
    if 'confidence_avg' in payload:
        confidence = payload['confidence_avg']
        if confidence is not None and (not number(confidence) or not 0 <= confidence <= 1):
            raise ValueError("confidence_avg phải null hoặc trong [0,1]")
        if (payload['raw_count'] == 0) != (confidence is None):
            raise ValueError("confidence_avg phải null đúng khi không có detection")
    for key in ('model', 'cmd_id', 'detail'):
        if key in payload and (not isinstance(payload[key], str) or not payload[key]):
            raise ValueError(f"{key} phải là chuỗi không rỗng")
    return payload


def build_payload(topic: str, bus_id: str, **values: Any) -> dict[str, Any]:
    return validate_payload(topic, dict(ts=now_ms(), bus_id=bus_id, node='vision', **values))


def parse_command(data: bytes | str | dict[str, Any]) -> dict[str, Any]:
    try:
        command = json.loads(data) if isinstance(data, (bytes, str)) else data
    except (ValueError, UnicodeError) as exc:
        raise ValueError("Lệnh không phải JSON UTF-8 hợp lệ") from exc
    if not isinstance(command, dict) or set(command) != {'cmd_id', 'ts', 'action', 'params', 'issued_by'}:
        raise ValueError("Lệnh thiếu hoặc thừa trường")
    if not isinstance(command['cmd_id'], str) or not command['cmd_id'].strip():
        raise ValueError("cmd_id phải là chuỗi không rỗng")
    if not nonnegative_int(command['ts']):
        raise ValueError("ts phải là epoch milliseconds không âm")
    if not isinstance(command['action'], str) or command['action'] not in ('STREAM_START', 'STREAM_STOP', 'PAUSE', 'RESUME'):
        raise ValueError("action không được hỗ trợ")
    params = command['params']
    if not isinstance(params, dict) or set(params) - ({'fps'} if command['action'] == 'STREAM_START' else set()):
        raise ValueError('params không hợp lệ')
    if 'fps' in params and not number(params['fps']):
        raise ValueError('fps không hợp lệ')
    if not isinstance(command['issued_by'], str) or not command['issued_by'].strip():
        raise ValueError("issued_by phải là chuỗi không rỗng")
    return command
