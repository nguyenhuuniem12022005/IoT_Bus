import http.client
import numpy as np
from vision_node.mjpeg import MjpegServer


def test_stream_and_unavailable():
    server = MjpegServer(port=0)
    server.start()
    def connect():
        return http.client.HTTPConnection('127.0.0.1', server.http.server_port, timeout=3)
    try:
        client = connect()
        client.request('GET', '/stream.mjpg')
        assert client.getresponse().status == 503
        client.close()
        server.publish(np.zeros((40, 60, 3), dtype=np.uint8))
        client = connect()
        client.request('GET', '/stream.mjpg')
        response = client.getresponse()
        assert response.status == 200
        assert 'boundary=frame' in response.getheader('Content-Type')
        assert response.readline() == b'--frame\r\n'
        assert response.readline() == b'Content-Type: image/jpeg\r\n'
        length = int(response.readline().split(b':')[1])
        assert response.readline() == b'\r\n'
        assert response.read(length).startswith(b'\xff\xd8')
        client.close()
        server.clear()
        client = connect()
        client.request('GET', '/stream.mjpg')
        assert client.getresponse().status == 503
        client.close()
    finally:
        server.close()
