import {api} from './api.js';

// Ảnh MJPEG do trình duyệt giải mã; nhịp WebSocket chỉ theo dõi mất tín hiệu.
export function createVideo() {
  const image = document.getElementById('live-video');
  const badge = document.getElementById('video-badge');
  const toggle = document.getElementById('video-toggle');
  const panel = document.getElementById('video-panel');
  let bus, paused = false, online = false, version = 0, retry;
  let lastFrame = 0, started = 0, loaded = false, failed = false;

  function render() {
    const fresh = lastFrame && performance.now() - lastFrame <= 3000;
    // Một số trình duyệt không phát load cho từng phần trong MJPEG.
    loaded ||= image.hasAttribute('src') && image.naturalWidth > 0;
    const live = !paused && !document.hidden && online && loaded && fresh && !failed;
    badge.textContent = paused ? 'Đã tạm dừng' : !online ? 'Node camera offline' :
      live ? 'TRỰC TIẾP' : failed || (started && performance.now() - (lastFrame || started) > 3000) ?
      'Không có tín hiệu' : 'Đang kết nối…';
    badge.classList.toggle('online', Boolean(live));
    toggle.textContent = paused ? 'Tiếp tục' : 'Tạm dừng';
  }

  function close() {
    version++;
    clearTimeout(retry);
    image.removeAttribute('src');
    loaded = false;
    lastFrame = 0;
    render();
  }

  async function open() {
    close();
    if (!bus || paused || document.hidden) return;
    const attempt = version;
    started = performance.now();
    failed = false;
    render();
    try {
      await api(`/api/buses/${encodeURIComponent(bus)}/video-session`, {method: 'POST'});
      if (version !== attempt || paused || document.hidden) return;
      image.src = `/api/buses/${encodeURIComponent(bus)}/stream.mjpg?t=${Date.now()}`;
    } catch {
      if (version !== attempt) return;
      failed = true;
      render();
      retry = setTimeout(open, 5000);
    }
  }

  image.onload = () => { loaded = true; render(); };
  image.onerror = () => {
    if (!image.hasAttribute('src')) return;
    failed = true;
    render();
    clearTimeout(retry);
    retry = setTimeout(open, 5000);
  };
  toggle.onclick = () => { paused = !paused; paused ? close() : open(); render(); };
  document.getElementById('video-fullscreen').onclick = async () => {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await panel.requestFullscreen();
    } catch { badge.textContent = 'Trình duyệt không hỗ trợ toàn màn hình'; }
  };
  document.addEventListener('visibilitychange', () => document.hidden ? close() : open());
  window.addEventListener('pagehide', close);
  window.addEventListener('pageshow', event => { if (event.persisted) open(); });
  setInterval(render, 250);

  return {
    select(id) { if (bus !== id) paused = false; bus = id; open(); },
    state(value) { online = Boolean(value); render(); },
    frame() { if (image.hasAttribute('src')) { lastFrame = performance.now(); render(); } },
    reconnect() { open(); },
  };
}
