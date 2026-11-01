"""Thread chụp chỉ giữ khung mới nhất và tự phục hồi nguồn."""
import logging
import sys
import threading
import time
from pathlib import Path
from typing import Any

LOG = logging.getLogger(__name__)


class CameraSource:
    def __init__(self, source: int | str, width: int = 640, height: int = 480,
                 loop_video: bool = True) -> None:
        self.source, self.width, self.height = source, width, height
        self.loop_video = loop_video
        self.is_file = isinstance(source, str) and Path(source).is_file()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._frame: Any = None
        self._last_frame = float('-inf')
        self._sequence = 0
        self._consumed = 0
        self._thread: threading.Thread | None = None
        self.ended = False

    @property
    def camera_ok(self) -> bool:
        with self._lock:
            return time.monotonic() - self._last_frame <= 2 and not self.ended

    def start(self) -> None:
        self._thread = threading.Thread(target=self._capture, daemon=True, name='camera')
        self._thread.start()

    def read(self) -> tuple[bool, Any]:
        with self._lock:
            if self._sequence == self._consumed or time.monotonic() - self._last_frame > 2:
                return False, None
            self._consumed = self._sequence
            return True, self._frame.copy()

    def latest(self) -> tuple[int, Any]:
        # Độc giả video không tiêu thụ khung dành cho vòng suy luận.
        with self._lock:
            if self.ended or self._frame is None or time.monotonic() - self._last_frame > 2:
                return self._sequence, None
            return self._sequence, self._frame.copy()

    def _open(self) -> Any:
        import cv2
        if isinstance(self.source, int):
            capture = cv2.VideoCapture(self.source, cv2.CAP_DSHOW if sys.platform == 'win32' else cv2.CAP_ANY)
        elif self.is_file:
            capture = cv2.VideoCapture(self.source)
        else:
            capture = cv2.VideoCapture(self.source, cv2.CAP_FFMPEG, [
                cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 2000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 2000])
        if isinstance(self.source, int):
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        return capture

    def _capture(self) -> None:
        import cv2
        backoff = 1.
        while not self._stop.is_set():
            capture = None
            try:
                capture = self._open()
                if not capture.isOpened():
                    raise OSError('Không mở được camera')
                last_success = time.monotonic()
                fps = capture.get(cv2.CAP_PROP_FPS)
                period = 1 / fps if self.is_file and 0 < fps < 240 else .001
                deadline = time.monotonic()
                while not self._stop.is_set():
                    ok, frame = capture.read()
                    if ok:
                        last_success = time.monotonic()
                        backoff = 1.
                        with self._lock:
                            self._frame = frame
                            self._last_frame = last_success
                            self._sequence += 1
                    elif self.is_file:
                        if not self.loop_video:
                            self.ended = True
                            return
                        if not capture.set(cv2.CAP_PROP_POS_FRAMES, 0):
                            raise OSError('Không tua lại được video')
                    if time.monotonic() - last_success > 2:
                        raise OSError('Không nhận được khung trong 2 giây')
                    deadline = max(deadline + period, time.monotonic())
                    self._stop.wait(max(.001, deadline - time.monotonic()))
            except Exception as exc:
                LOG.warning('Camera lỗi: %s; thử lại sau %.1fs', exc, backoff)
                with self._lock:
                    self._last_frame = float('-inf')
            finally:
                if capture is not None:
                    capture.release()
            self._stop.wait(backoff)
            backoff = min(10., backoff * 2)

    def close(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        if self._thread and self._thread.is_alive():
            LOG.warning('Driver camera chưa trả quyền điều khiển khi đóng')
