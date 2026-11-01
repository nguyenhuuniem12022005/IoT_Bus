import {api, token} from './api.js';
if (token()) location.replace('/');
document.getElementById('login-form').addEventListener('submit', async event => {
  event.preventDefault();
  const button = event.target.querySelector('button');
  const error = document.getElementById('login-error');
  button.disabled = true; error.hidden = true;
  try {
    const result = await api('/api/auth/login', {method: 'POST', body: JSON.stringify({
      username: document.getElementById('username').value.trim(), password: document.getElementById('password').value
    })});
    sessionStorage.setItem('smartbus-token', result.access_token);
    location.replace('/');
  } catch (err) { error.textContent = err.message; error.hidden = false; }
  finally { button.disabled = false; }
});
