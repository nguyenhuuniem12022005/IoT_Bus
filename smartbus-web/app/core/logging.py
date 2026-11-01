import logging
import re
import sys


class TokenFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Uvicorn ghi URL bắt tay WebSocket vào error logger, không chỉ access logger.
        record.msg = re.sub(r"([?&]token=)[^&\s\"']+", r"\1[REDACTED]", record.getMessage())
        record.args = ()
        return True


def configure_logging() -> None:
    # Giữ tiếng Việt khi PowerShell chuyển stdout/stderr sang pipe dùng CP1252.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("uvicorn.error").addFilter(TokenFilter())
    for handler in logging.getLogger().handlers:
        handler.addFilter(TokenFilter())
    # URL WebSocket chứa JWT; không ghi access log vào console.
    logging.getLogger("uvicorn.access").disabled = True
