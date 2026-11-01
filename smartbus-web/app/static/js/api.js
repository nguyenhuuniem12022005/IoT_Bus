export function token() { return sessionStorage.getItem('smartbus-token'); }
export function logout() { sessionStorage.clear(); location.replace('/login.html'); }
export async function api(path, options = {}) {
  const headers = {'Content-Type': 'application/json', ...options.headers};
  if (token()) headers.Authorization = `Bearer ${token()}`;
  const response = await fetch(path, {...options, headers});
  if (response.status === 401 && path !== '/api/auth/login') { logout(); throw new Error('Phiên đăng nhập đã hết hạn.'); }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = Array.isArray(data.detail) ? 'Dữ liệu không hợp lệ. Vui lòng kiểm tra lại.' : data.detail;
    throw new Error(message || `Không thể hoàn tất yêu cầu (${response.status}).`);
  }
  return data;
}
