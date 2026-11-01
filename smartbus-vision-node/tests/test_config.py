"""Kiểm tra thứ tự ưu tiên và lỗi cấu hình tiếng Việt."""
from pathlib import Path
import pytest
from vision_node.config import load_config, validate_config


def test_defaults_and_environment() -> None:
    config = load_config(environ={})
    assert config['bus_id'] == 'bus01' and config['source'] == 0
    assert config['model']['conf'] == .40 and config['infer_fps'] == 5
    config = load_config(environ={'BUS_ID': 'bus02', 'VISION_SOURCE': '2', 'MQTT_TLS': 'true'})
    assert config['bus_id'] == 'bus02' and config['source'] == 2
    assert config['mqtt']['username'] == 'laptop-bus02' and config['mqtt']['port'] == 8883


def test_cli_wins() -> None:
    config = load_config(environ={'BUS_ID': 'old', 'VISION_SOURCE': '1'},
                         overrides={'bus_id': 'new', 'source': 'movie.mp4', 'preview': True})
    assert config['bus_id'] == 'new' and config['source'] == 'movie.mp4' and config['preview']


@pytest.mark.parametrize('env', [{'MQTT_TLS': 'yes'}, {'MQTT_PORT': 'abc'}, {'MQTT_PORT': '0'},
    {'BUS_ID': 'bad/+'}, {'MQTT_USERNAME': 'backend'}, {'LOG_LEVEL': 'bad'}])
def test_bad_environment(env: dict) -> None:
    with pytest.raises(ValueError, match='Cấu hình không hợp lệ'):
        load_config(environ=env)


@pytest.mark.parametrize('key,value', [('infer_fps', 0), ('frame_width', True),
    ('source', -1), ('preview', 'false'), ('roi', [[0, 0], [1, 1]])])
def test_bad_yaml(config: dict, key: str, value: object) -> None:
    config[key] = value
    with pytest.raises(ValueError):
        validate_config(config)


def test_missing_config(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match='Cấu hình không hợp lệ'):
        load_config(tmp_path / 'missing.yaml', environ={})


@pytest.mark.parametrize('key,value', [('lease_s', 0), ('max_kb', 0), ('jpeg_quality', 29), ('draw_boxes', 'yes')])
def test_stream_contract_limits(config: dict, key: str, value: object) -> None:
    config['stream'][key] = value
    with pytest.raises(ValueError):
        validate_config(config)
