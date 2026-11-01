"""LAN MJPEG server: encode once, keep only the latest frame."""
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class MjpegServer:
    def __init__(self, host="127.0.0.1", port=8081):
        self.condition = threading.Condition()
        self.jpeg = None
        self.sequence = 0
        self.updated = 0.
        self.closed = False
        self.slots = threading.BoundedSemaphore(8)
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                if self.path != '/stream.mjpg':
                    self.send_error(404)
                    return
                if not owner.slots.acquire(blocking=False):
                    self.send_error(503, 'Too many viewers')
                    return
                try:
                    self.connection.settimeout(5)
                    with owner.condition:
                        if owner.jpeg is None or time.monotonic()-owner.updated > 3:
                            self.send_error(503, 'Camera unavailable or paused')
                            return
                    self.send_response(200)
                    self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
                    self.send_header('Cache-Control', 'no-store')
                    self.send_header('Connection', 'close')
                    self.end_headers()
                    sequence = -1
                    while not owner.closed:
                        with owner.condition:
                            owner.condition.wait_for(lambda: owner.closed or owner.sequence != sequence, timeout=3)
                            if owner.closed or owner.jpeg is None or time.monotonic()-owner.updated > 3:
                                break
                            if sequence == owner.sequence:
                                continue
                            sequence, jpeg = owner.sequence, owner.jpeg
                        self.wfile.write(b'--frame\r\nContent-Type: image/jpeg\r\nContent-Length: ' + str(len(jpeg)).encode() + b'\r\n\r\n' + jpeg + b'\r\n')
                        self.wfile.flush()
                except (OSError, TimeoutError):
                    pass
                finally:
                    owner.slots.release()
                    self.close_connection = True

        self.http = ThreadingHTTPServer((host, port), Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)

    def start(self):
        self.thread.start()

    def publish(self, frame):
        import cv2
        ok, data = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        if ok:
            with self.condition:
                self.jpeg = data.tobytes()
                self.updated = time.monotonic()
                self.sequence += 1
                self.condition.notify_all()

    def clear(self):
        with self.condition:
            self.jpeg = None
            self.sequence += 1
            self.condition.notify_all()

    def close(self):
        with self.condition:
            self.closed = True
            self.condition.notify_all()
        if self.thread.is_alive():
            self.http.shutdown()
            self.thread.join(timeout=5)
        self.http.server_close()
