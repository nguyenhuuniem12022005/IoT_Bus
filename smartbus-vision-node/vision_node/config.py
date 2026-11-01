"""Nạp YAML, dotenv, biến môi trường và ghi đè CLI."""
import math
import os
import re
from pathlib import Path
from typing import Any, Mapping
import yaml
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def boolean(value: Any) -> bool:
    if type(value) is bool:
        return value
    if isinstance(value, str) and value.lower() in ('true', 'false'):
        return value.lower() == 'true'
    raise ValueError("Giá trị boolean phải là true hoặc false")


def validate_config(config: dict[str, Any]) -> None:
    if not isinstance(config.get('bus_id'), str) or not re.fullmatch(r'[A-Za-z0-9_-]+', config['bus_id']):
        raise ValueError("bus_id chỉ được chứa chữ, số, dấu - và _")
    if 'crossing' in config:
        from .counter import DirectionalCounter
        DirectionalCounter(**config['crossing'])
    source = config['source']
    if not ((type(source) is int and source >= 0) or (isinstance(source, str) and source.strip())):
        raise ValueError("source phải là chỉ số camera hoặc đường dẫn/URL")
    for key in ('loop_video', 'preview'):
        if type(config[key]) is not bool:
            raise ValueError(f"{key} phải là boolean")
    integers = [config['frame_width'], config['frame_height'], config['model']['imgsz'],
                config['counter']['window'], config['counter']['min_change_frames']]
    if any(type(v) is not int or v < 1 for v in integers):
        raise ValueError("Kích thước và tham số counter phải là số nguyên dương")
    positives = [config['infer_fps'], *config['publish'].values()]
    if any(type(v) not in (float, int) or not math.isfinite(v) or v <= 0 for v in positives):
        raise ValueError("FPS và chu kỳ phải là số dương hữu hạn")
    model = config['model']
    if not isinstance(model['path'], str) or not model['path'] or model['device'] not in ('auto', 'cpu', 'cuda:0'):
        raise ValueError("Đường dẫn model hoặc device không hợp lệ")
    for key in ('conf', 'iou'):
        if type(model[key]) not in (float, int) or not 0 <= model[key] <= 1:
            raise ValueError(f"model.{key} phải nằm trong [0,1]")
    roi = config['roi']
    if not isinstance(roi, list) or (roi and len(roi) < 3):
        raise ValueError("ROI phải rỗng hoặc có ít nhất 3 đỉnh")
    for point in roi:
        if not isinstance(point, list) or len(point) != 2 or any(type(v) not in (float, int) or not 0 <= v <= 1 for v in point):
            raise ValueError("Toạ độ ROI phải thuộc [0,1]")
    if roi and abs(sum(roi[i-1][0]*p[1] - p[0]*roi[i-1][1] for i,p in enumerate(roi))) < 1e-9:
        raise ValueError("Đa giác ROI phải có diện tích dương")
    from .streamer import Streamer
    Streamer(**config['stream'])
    mqtt = config['mqtt']
    if not mqtt['host'] or not 1 <= mqtt['port'] <= 65535:
        raise ValueError("Host hoặc cổng MQTT không hợp lệ")
    if mqtt['username'] != f"laptop-{config['bus_id']}":
        raise ValueError("MQTT_USERNAME phải trùng laptop-{bus_id}")
    if config['log_level'] not in ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'):
        raise ValueError("LOG_LEVEL không hợp lệ")


def load_config(path: str | Path = ROOT / 'config/config.yaml',
                overrides: Mapping[str, Any] | None = None,
                environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    try:
        config = yaml.safe_load(Path(path).read_text(encoding='utf-8'))
        env = dict(dotenv_values(ROOT / '.env'))
        env.update(os.environ if environ is None else environ)
        for env_key, config_key in [('BUS_ID', 'bus_id'), ('VISION_SOURCE', 'source')]:
            if env.get(env_key):
                config[config_key] = env[env_key]
        config.update({k: v for k, v in (overrides or {}).items() if v is not None})
        if isinstance(config['source'], str) and config['source'].isdigit():
            config['source'] = int(config['source'])
        tls = boolean(env.get('MQTT_TLS', 'false'))
        config['mqtt'] = dict(host=env.get('MQTT_HOST', 'localhost'),
                              port=int(env.get('MQTT_PORT', '8883' if tls else '1883')),
                              tls=tls, username=env.get('MQTT_USERNAME') or f"laptop-{config['bus_id']}",
                              password=env.get('MQTT_PASSWORD', ''))
        config['log_level'] = env.get('LOG_LEVEL', 'INFO').upper()
        validate_config(config)
        return config
    except (OSError, KeyError, TypeError, AttributeError, ValueError, yaml.YAMLError) as exc:
        raise ValueError(f"Cấu hình không hợp lệ: {exc}") from exc
