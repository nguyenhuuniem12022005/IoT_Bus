"""Thiết lập log console và tệp xoay vòng."""
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_console() -> None:
    """Giữ tiếng Việt khi stdout/stderr được chuyển hướng trên Windows."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='backslashreplace')


def setup_logging(level: str = "INFO", log_dir: str = "logs") -> None:
    configure_console()
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    handlers = [logging.StreamHandler(), RotatingFileHandler(
        Path(log_dir) / 'vision_node.log', maxBytes=2_000_000, backupCount=3, encoding='utf-8')]
    logging.basicConfig(level=level, handlers=handlers,
                        format='%(asctime)s %(levelname)s %(name)s: %(message)s', force=True)
