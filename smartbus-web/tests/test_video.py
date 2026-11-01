"""Kiểm tra người xem, khung nhị phân, phân quyền và mô phỏng video."""
import asyncio
import io
import json
import threading
import time
from types import SimpleNamespace
import pytest
from PIL import Image
from fastapi import HTTPException
from app.core.security import create_token
from app.services.video_service import mjpeg_part
from app.mqtt_bridge.client import MQTTBridge
from scripts.simulate_devices import SimulatedNode


@pytest.mark.asyncio
async def test_viewers_start_renew_stop_and_audit(app):
    service = app.state.video
    app.state.settings.video_renew_s = .05
    app.state.settings.video_stop_grace_s = .05
    a, b = await service.add('bus01', 'viewer'), await service.add('bus01', 'admin')
    actions = lambda: [p['action'] for _, p in app.state.bridge.messages]
    try:
        assert actions() == ['STREAM_START']
        async def renewed():
            while len(actions()) < 2:
                await asyncio.sleep(.01)
        await asyncio.wait_for(renewed(), timeout=2)
        assert set(actions()) == {'STREAM_START'}
        await service.remove('bus01', a)
        assert len(service.viewers['bus01']) == 1 and 'STREAM_STOP' not in actions()
        await service.remove('bus01', b)
        async def stopped():
            while 'STREAM_STOP' not in actions():
                await asyncio.sleep(.01)
        await asyncio.wait_for(stopped(), timeout=2)
        assert actions()[-1] == 'STREAM_STOP' and actions().count('STREAM_STOP') == 1
        assert await app.state.db.commands.count_documents({}) == 0
        rows = await app.state.db.audit_logs.find({}).to_list(None)
        assert [r['action'] for r in rows].count('VIDEO_VIEW_START') == 2
        assert [r['action'] for r in rows].count('VIDEO_VIEW_STOP') == 2
        assert {r['actor'] for r in rows} == {'admin', 'viewer'}
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_limit_latest_only_count_unaffected_and_grace(app, vision):
    service = app.state.video
    app.state.settings.video_stop_grace_s = .05
    viewers = [await service.add('bus01', 'viewer') for _ in range(5)]
    try:
        with pytest.raises(HTTPException) as error:
            await service.add('bus01', 'viewer')
        assert error.value.status_code == 429
        for n in range(100):
            await app.state.handler.handle('smartbus/bus01/vision/frame', b'\xff\xd8' + bytes([n]) + b'\xff\xd9')
        assert all(v.queue.qsize() == 1 for v in viewers)
        assert await viewers[0].queue.get() == b'\xff\xd8c\xff\xd9'
        await app.state.handler.handle('smartbus/bus01/vision/count', json.dumps(vision).encode())
        assert app.state.states.get('bus01')['vision_count'] == 2
        for v in viewers:
            await service.remove('bus01', v)
        new = await service.add('bus01', 'viewer')
        await asyncio.sleep(.1)
        assert not any(p['action'] == 'STREAM_STOP' for _, p in app.state.bridge.messages)
        assert new.queue.empty()
    finally:
        await service.close()


def test_mjpeg_boundary_and_content_length():
    raw = b'\xff\xd8binary\x00\xff\xd9'
    header, body = mjpeg_part(raw).split(b'\r\n\r\n')
    assert header == b'--frame\r\nContent-Type: image/jpeg\r\nContent-Length: ' + str(len(raw)).encode()
    assert body == raw + b'\r\n'


@pytest.mark.asyncio
@pytest.mark.parametrize('with_frame', [True, False])
async def test_http_disconnect_cleans_viewer(app, with_frame):
    incoming = asyncio.Queue()
    await incoming.put({'type': 'http.request', 'body': b'', 'more_body': False})
    sent = []
    token = create_token('viewer', app.state.settings)
    scope = {'type': 'http', 'asgi': {'version': '3.0', 'spec_version': '2.3'},
             'http_version': '1.1', 'method': 'GET', 'scheme': 'http',
             'path': '/api/buses/bus01/stream.mjpg', 'raw_path': b'/api/buses/bus01/stream.mjpg',
             'query_string': b'', 'root_path': '', 'server': ('test', 80), 'client': ('test', 123),
             'headers': [(b'authorization', ('Bearer ' + token).encode())]}
    async def send(message):
        sent.append(message)
        if message['type'] == 'http.response.start':
            if with_frame:
                await app.state.video.frame('bus01', b'\xff\xd8test\xff\xd9')
            else:
                await incoming.put({'type': 'http.disconnect'})
        elif message['type'] == 'http.response.body':
            await incoming.put({'type': 'http.disconnect'})
    try:
        await asyncio.wait_for(app(scope, incoming.get, send), timeout=3)
        await asyncio.sleep(.02)
        assert sent[0]['status'] == 200
        assert not app.state.video.viewers.get('bus01')
        if with_frame:
            assert any(m.get('body', b'').startswith(b'--frame\r\n') for m in sent)
    finally:
        await app.state.video.close()


@pytest.mark.asyncio
async def test_mqtt_burst_bounded_without_blocking_count(app):
    gate, entered, count_received = asyncio.Event(), asyncio.Event(), asyncio.Event()
    received = []
    async def handle(topic, payload):
        if topic.endswith('/vision/frame'):
            entered.set()
            await gate.wait()
            received.append(payload)
        else:
            count_received.set()
    bridge = MQTTBridge(app.state.settings, SimpleNamespace(handle=handle), asyncio.get_running_loop())
    def emit(suffix, payload):
        bridge.on_message(bridge.client, None, SimpleNamespace(topic='smartbus/bus01/' + suffix, payload=payload))
    emit('vision/frame', b'first')
    await asyncio.wait_for(entered.wait(), 1)
    for n in range(1000):
        emit('vision/frame', str(n).encode())
    emit('vision/count', b'count')
    await asyncio.wait_for(count_received.wait(), 1)
    assert len(bridge.video_pending) == 1 and bridge.video_pending['smartbus/bus01/vision/frame'] == b'999'
    gate.set()
    await asyncio.gather(*(asyncio.wrap_future(f) for f in list(bridge.pending)))
    assert received == [b'first', b'999']
    assert not bridge.video_pending and not bridge.video_scheduled


@pytest.mark.asyncio
async def test_video_auth_cookie_scope_and_http_limit(client, app):
    path = '/api/buses/bus01/stream.mjpg'
    assert (await client.get(path)).status_code == 401
    headers = {'Authorization': 'Bearer ' + create_token('viewer', app.state.settings)}
    response = await client.post('/api/buses/bus01/video-session', headers=headers)
    assert response.status_code == 200
    cookie = response.headers['set-cookie']
    assert 'HttpOnly' in cookie and 'SameSite=strict' in cookie and 'Path=' + path in cookie
    assert (await client.get('/api/buses')).status_code == 401
    for _ in range(5):
        await app.state.video.add('bus01', 'viewer')
    try:
        assert (await client.get(path)).status_code == 429
    finally:
        await app.state.video.close()


@pytest.mark.asyncio
async def test_simulator_moving_jpeg_pause_stop_and_lease(app, monkeypatch):
    node = SimulatedNode('vision', 'bus01', 'normal', 100, app.state.settings, threading.Event())
    now = [100.]
    monkeypatch.setattr('scripts.simulate_devices.time.monotonic', lambda: now[0])
    published = []
    node.connected = True
    node.client.publish = lambda topic, payload, **kwargs: (published.append((topic, payload)) or SimpleNamespace(is_published=lambda: True, rc=0))
    def command(action):
        message = SimpleNamespace(topic='smartbus/bus01/cmd/vision', payload=json.dumps({
            'cmd_id': str(len(published)), 'ts': 1, 'action': action, 'params': {}, 'issued_by': 'test'}).encode())
        node.on_message(node.client, None, message)
    command('STREAM_START')
    node.video_tick()
    now[0] += .2
    node.video_tick()
    frames = [p for t, p in published if t.endswith('/vision/frame')]
    assert len(frames) == 2 and frames[0] != frames[1]
    assert Image.open(io.BytesIO(frames[0])).size == (480, 360)
    now[0] = 131
    node.video_tick()
    assert not node.streaming()
    assert json.loads([p for t, p in published if t.endswith('/vision/status')][-1])['streaming'] is False
    command('STREAM_START')
    command('PAUSE')
    assert not node.streaming()
    command('RESUME')
    command('STREAM_START')
    command('STREAM_STOP')
    assert not node.streaming()
