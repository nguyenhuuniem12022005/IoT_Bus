import {token, logout} from './api.js';
export function connect(onMessage, onStatus) {
  let socket, timer, attempts = 0, stopped = false;
  function open() {
    if (stopped || !token()) return;
    onStatus(false);
    socket = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws?token=${encodeURIComponent(token())}`);
    socket.onopen = () => { attempts = 0; onStatus(true); };
    socket.onmessage = event => { try { onMessage(JSON.parse(event.data)); } catch { /* Bỏ qua bản tin không hợp lệ. */ } };
    socket.onclose = event => {
      onStatus(false);
      if (event.code === 4401) { logout(); return; }
      if (!stopped) timer = setTimeout(open, Math.min(30000, 1000 * 2 ** attempts++) + Math.random() * 500);
    };
    socket.onerror = () => socket.close();
  }
  open();
  return () => { stopped = true; clearTimeout(timer); socket?.close(); };
}
