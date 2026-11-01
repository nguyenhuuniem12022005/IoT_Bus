import {api, token, logout} from './api.js';
import {connect} from './ws.js';
import {createVideo} from './video.js';
const video = createVideo();
const $ = id => document.getElementById(id);
const states = new Map();
let user, selected, history = [], events = [], activeAlerts = [], selectionVersion = 0, sound = false, audio, lastBeep = 0;
const labels = {RUNNING:'Đang chạy',CHECKING:'Đang kiểm tra',WARNING:'Cảnh báo',CRITICAL:'Khẩn cấp',SAFE:'An toàn',
  SAFETY_NOT_CONFIRMED:'Chưa bấm Safety',PIR_MOTION_DETECTED:'PIR phát hiện chuyển động',IR_COUNT_POSITIVE:'IR còn hành khách',VISION_PERSON_DETECTED:'Camera thấy người',
  BOARD:'Hành khách lên xe',ALIGHT:'Hành khách xuống xe',IGNITION_ON:'Bật máy',IGNITION_OFF:'Tắt máy',PIR_MOTION:'Phát hiện chuyển động',SAFETY_CONFIRMED:'Đã bấm Safety',STATE_CHANGED:'Đổi trạng thái',FAN_CHANGED:'Đổi trạng thái quạt',COUNT_RESET:'Đặt lại sĩ số',
  SENT:'Đã gửi, đang chờ phản hồi',ACKED_OK:'Thành công',ACKED_FAIL:'Thiết bị từ chối',TIMEOUT:'Quá hạn phản hồi'};
const eventTones = {BOARD:'tone-safe',ALIGHT:'tone-run',SAFETY_CONFIRMED:'tone-safe',PIR_MOTION:'tone-check',IGNITION_OFF:'tone-check',IGNITION_ON:'tone-run'};
const commandTones = {SENT:'pending',ACKED_OK:'ok',ACKED_FAIL:'fail',TIMEOUT:'fail'};
const actionNames = Object.fromEntries([...document.querySelectorAll('[data-action]')].map(b => [b.dataset.action, b.textContent]));
const text = (id, value) => { $(id).textContent = value; };
const time = ts => ts ? new Date(ts).toLocaleString('vi-VN') : 'Chưa có dữ liệu';
function showError(error) { text('error', error.message); $('error').hidden = false; }
function cell(row, value) { const td = document.createElement('td'); td.textContent = value; row.append(td); return td; }
function el(tag, className, value) { const node = document.createElement(tag); if (className) node.className = className; if (value !== undefined) node.textContent = value; return node; }
function icon(id) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg'), use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
  svg.setAttribute('class', 'i'); svg.setAttribute('aria-hidden', 'true'); use.setAttribute('href', `#${id}`); svg.append(use); return svg;
}
function ask(message, {title = 'Xác nhận thao tác', ok = 'Xác nhận', danger = false, note = false} = {}) {
  const dialog = $('confirm-dialog');
  if (!dialog.showModal) return Promise.resolve(note ? prompt(message, '') : (confirm(message) ? '' : null));
  text('confirm-title', title); text('confirm-message', message); text('confirm-ok', ok);
  $('confirm-note-field').hidden = !note; $('confirm-note').value = ''; dialog.classList.toggle('is-danger', danger); dialog.returnValue = '';
  dialog.showModal();
  (note ? $('confirm-note') : danger ? dialog.querySelector('[value="cancel"]') : $('confirm-ok')).focus();
  return new Promise(resolve => dialog.addEventListener('close', () => resolve(dialog.returnValue === 'ok' ? (note ? $('confirm-note').value : '') : null), {once: true}));
}
function addBus(bus) {
  if (!states.has(bus.bus_id)) { const option = document.createElement('option'); option.value = bus.bus_id; option.textContent = bus.bus_id; $('bus').append(option); }
  states.set(bus.bus_id, bus);
}
function renderState() {
  const s = states.get(selected); if (!s) return;
  video.state(s.vision_online);
  text('ir-count', s.ir_count); text('vision-count', s.vision_count);
  text('state', s.updated_at ? labels[s.state] || s.state : 'Chưa có dữ liệu'); $('state').className = `pill ${s.state}`;
  $('mismatch').hidden = !s.count_mismatch;
  for (const li of document.querySelectorAll('#route li')) { const on = Boolean(s.updated_at) && li.dataset.stop === s.state; li.classList.toggle('current', on); if (on) li.setAttribute('aria-current', 'step'); else li.removeAttribute('aria-current'); }
  const facts = [['i-key','Động cơ',s.ignition?'Đang bật':'Đã tắt',s.ignition&&'on'],['i-motion','PIR',s.pir_motion?'Có chuyển động':'Không',s.pir_motion&&'on'],['i-shield','Safety',s.safety_confirmed?'Đã xác nhận':'Chưa xác nhận',s.safety_confirmed&&'ok'],['i-bell','Còi',s.buzzer?'Đang bật':'Đã tắt',s.buzzer&&'alert'],['i-led','LED',({off:'Tắt',green:'Xanh',red:'Đỏ',red_blink:'Đỏ nhấp nháy'})[s.led],null],['i-fan','Quạt',s.fan?'Đang bật':'Đã tắt',s.fan&&'on']];
  $('vehicle-fields').replaceChildren();
  for (const [id,key,value,tone] of facts) {
    const div=el('div',tone||''),body=el('div','fact-text'),dt=el('dt','',key),dd=el('dd','',value);
    if(id==='i-led')dd.prepend(el('span',`led-swatch led-${s.led}`));
    body.append(dt,dd);div.append(icon(id),body);$('vehicle-fields').append(div);
  }
  for (const node of ['sensor','vision']) { text(`${node}-status`,s[`${node}_online`]?'Trực tuyến':'Ngoại tuyến');$(`${node}-status`).className=`pill ${s[`${node}_online`]?'online':''}`; }
  for (const source of ['pir','ir','vision']) $(`presence-${source}`).classList.toggle('active', Boolean(s.presence?.[source]));
  text('rssi',`RSSI ${s.wifi_rssi ?? '—'} dBm`); text('fps',`${s.vision_fps.toFixed(1)} FPS · ${s.vision_fresh?'Dữ liệu mới':'Dữ liệu cũ / chưa nhận'}`);
  $('camera-info').hidden = !(s.vision_count>0 && s.vision_fresh && !s.sensor_online);
  text('camera-info',`Camera đếm còn ${s.vision_count} người trên xe — mất kết nối cảm biến`); renderAges();
}
function renderAges() {
  const s=states.get(selected); if(!s)return;
  for(const node of ['sensor','vision']) text(`${node}-age`,s[`${node}_updated_at`]?`Cập nhật ${Math.max(0,Math.floor((Date.now()-s[`${node}_updated_at`])/1000))} giây trước`:'Chưa nhận dữ liệu');
}
function renderBanner() {
  const alert=activeAlerts.filter(a=>a.status==='ACTIVE').sort((a,b)=>(b.level==='CRITICAL')-(a.level==='CRITICAL'))[0];
  $('banner').hidden=!alert;
  if(alert){text('banner',`${labels[alert.level]} · ${alert.reasons.map(r=>labels[r]||r).join(' • ')} · ${time(alert.ts)}`);$('banner').className=alert.level==='CRITICAL'?'critical':'';}
}
function beep() {
  if(!sound || !activeAlerts.some(a=>a.status==='ACTIVE') || Date.now()-lastBeep<5000)return;
  lastBeep=Date.now(); const oscillator=audio.createOscillator(),gain=audio.createGain();oscillator.connect(gain);gain.connect(audio.destination);oscillator.frequency.value=740;gain.gain.value=.08;oscillator.start();oscillator.stop(audio.currentTime+.25);
}
function drawChart() {
  const canvas=$('chart'),bounds=canvas.getBoundingClientRect(),ratio=devicePixelRatio||1;
  if(!bounds.width)return;
  canvas.width=bounds.width*ratio;canvas.height=260*ratio;
  const ctx=canvas.getContext('2d');ctx.scale(ratio,ratio);const w=bounds.width,h=260,p=32;
  history=history.filter(x=>x.ts>=Date.now()-3600000).slice(-500);
  $('chart-empty').hidden=history.length>0;
  const max=Math.max(4,Math.ceil(Math.max(0,...history.map(x=>Math.max(x.ir_count,x.vision_count)))/4)*4),start=history[0]?.ts||Date.now()-3600000,end=Math.max(Date.now(),start+1000);
  ctx.font='500 11px "Be Vietnam Pro","Segoe UI",sans-serif';ctx.fillStyle='#5d6d7d';ctx.lineWidth=1;
  for(let i=0;i<=4;i++){const y=Math.round(p+(h-2*p)*i/4)+.5;ctx.strokeStyle=i===4?'#c9d3dc':'#e8ecf0';ctx.setLineDash(i===4?[]:[3,4]);ctx.beginPath();ctx.moveTo(p,y);ctx.lineTo(w-8,y);ctx.stroke();ctx.fillText(String(Math.round(max*(1-i/4))),6,y+4);}
  ctx.setLineDash([]);ctx.lineJoin='round';
  for(const [field,color,dash] of [['ir_count','#12202c',[]],['vision_count','#1d5bc4',[7,5]]]){
    let prevY,lastX;ctx.strokeStyle=color;ctx.lineWidth=2.25;ctx.setLineDash(dash);ctx.beginPath();
    history.forEach((row,i)=>{const x=p+(w-p-10)*(row.ts-start)/(end-start),y=h-p-(h-2*p)*row[field]/max;if(!i)ctx.moveTo(x,y);else{ctx.lineTo(x,prevY);ctx.lineTo(x,y);}prevY=y;lastX=x;});
    ctx.stroke();
    if(history.length){ctx.setLineDash([]);ctx.fillStyle='#fff';ctx.beginPath();ctx.arc(lastX,prevY,4,0,Math.PI*2);ctx.fill();ctx.stroke();}
  }
  ctx.fillStyle='#5d6d7d';ctx.fillText(new Date(start).toLocaleTimeString('vi-VN'),p,h-8);ctx.textAlign='right';ctx.fillText(new Date(end).toLocaleTimeString('vi-VN'),w-8,h-8);
}
function renderEvents() {
  $('events').replaceChildren();
  if(!events.length)$('events').append(el('p','empty','Chưa có sự kiện.'));
  for(const event of events.slice(0,50)){const row=el('div',`log-row ${eventTones[event.event]||''}`);row.append(el('time','',new Date(event.ts).toLocaleTimeString('vi-VN')),el('span','dot'),el('span','what',labels[event.event]||event.event),el('span','meta',`IR ${event.ir_count}`));$('events').append(row);}
}
async function refreshAlerts() {
  const bus=selected,rows=await api(`/api/alerts?bus_id=${encodeURIComponent(bus)}`);if(bus!==selected)return;
  activeAlerts=rows;renderBanner();$('alerts').replaceChildren();$('alerts-empty').hidden=rows.length>0;
  for(const alert of rows){const tr=document.createElement('tr');cell(tr,time(alert.created_at));cell(tr,'').append(el('span',`pill ${alert.level}`,labels[alert.level]));cell(tr,alert.reasons.map(r=>labels[r]||r).join(', '));cell(tr,'').append(alert.status==='ACTIVE'?el('span','pill pending','Đang diễn ra'):el('span','pill closed','Đã đóng'));const td=cell(tr,'');
    if(alert.acknowledged_by)td.append(el('span','acked',`Đã xác nhận: ${alert.acknowledged_by}`));
    if(!alert.acknowledged_by && user.role!=='viewer'){const b=document.createElement('button');b.type='button';b.textContent='Xác nhận đã xử lý';b.onclick=async()=>{const note=await ask('Việc xác nhận chỉ ghi nhận người xử lý và ghi chú, không tắt còi trên xe.',{title:'Xác nhận đã xử lý cảnh báo',ok:'Xác nhận đã xử lý',note:true});if(note===null)return;b.disabled=true;try{await api(`/api/alerts/${encodeURIComponent(alert.alert_id)}/ack`,{method:'POST',body:JSON.stringify({note})});await refreshAlerts();}catch(e){showError(e);b.disabled=false;}};td.append(b);}$('alerts').append(tr);}
}
async function refreshCommands() {
  const bus=selected,rows=await api(`/api/commands?bus_id=${encodeURIComponent(bus)}`);if(bus!==selected)return;
  $('command-history').replaceChildren();for(const cmd of rows.slice(0,10)){const row=el('div','log-row');row.append(el('time','',time(cmd.ts)),el('span'),el('span','what',actionNames[cmd.action]||cmd.action),el('span',`pill ${commandTones[cmd.status]||''}`,labels[cmd.status]||cmd.status));if(cmd.ack?.detail)row.append(el('span','detail',cmd.ack.detail));$('command-history').append(row);}
}
async function loadBus() {
  selected=$('bus').value;
  const version=++selectionVersion,bus=selected;history=[];events=[];activeAlerts=[];renderState();renderBanner();drawChart();renderEvents();video.select(selected);
  const results=await Promise.allSettled([api(`/api/buses/${bus}/history`),api(`/api/buses/${bus}/events?limit=50`),refreshAlerts(),refreshCommands()]);
  if(version!==selectionVersion)return;
  if(results[0].status==='fulfilled')history=[...results[0].value,...history].sort((a,b)=>a.ts-b.ts);else showError(results[0].reason);
  if(results[1].status==='fulfilled')events=[...events,...results[1].value].slice(0,50);else showError(results[1].reason);
  for(const r of results.slice(2))if(r.status==='rejected')showError(r.reason);
  drawChart();renderEvents();
}
async function refreshAudit() {try{const rows=await api('/api/audit-logs');$('audit').replaceChildren();for(const item of rows){const tr=document.createElement('tr');cell(tr,time(item.ts));cell(tr,item.actor);cell(tr,item.action);cell(tr,'').append(el('code','',JSON.stringify(item.detail)));$('audit').append(tr);}}catch(e){showError(e);}}
function receive(message) {
  if(message.type==='state'){addBus(message.data);if(message.bus_id===selected){renderState();history.push({ts:Date.now(),ir_count:message.data.ir_count,vision_count:message.data.vision_count});drawChart();}}
  if(message.bus_id!==selected)return;
  if(message.type==='node_status'){Object.assign(states.get(selected),message.data);renderState();}
  if(message.type==='event'){events.unshift(message.data);events=events.slice(0,50);renderEvents();}
  if(message.type==='video_frame')video.frame();
  if(message.type==='alert'){const i=activeAlerts.findIndex(a=>a.alert_id===message.data.alert_id);if(i<0)activeAlerts.push(message.data);else activeAlerts[i]=message.data;renderBanner();refreshAlerts().catch(showError);}
  if(message.type==='cmd_ack'){text('command-result',`${labels[message.data.status]||'Đã nhận phản hồi'}${message.data.detail?' · '+message.data.detail:''}`);refreshCommands().catch(showError);}
}
async function init() {
  if(!token()){logout();return;}
  user=await api('/api/auth/me');text('user',`${user.username} · ${{admin:'Quản trị',operator:'Điều hành',viewer:'Quan sát'}[user.role]}`);
  $('audit-tab').hidden=user.role!=='admin';$('viewer-note').hidden=user.role!=='viewer';$('control-buttons').hidden=user.role==='viewer';
  document.querySelectorAll('[data-action]').forEach(button=>{if(user.role==='viewer'||(button.hasAttribute('data-admin')&&user.role!=='admin'))button.hidden=true;button.onclick=async()=>{
    const action=button.dataset.action;if(await ask(`Xác nhận thao tác “${button.textContent}” trên xe ${selected}?`,{title:button.textContent,ok:button.textContent,danger:button.classList.contains('danger')})===null)return;
    const params=action==='FAN_ON'?{duration_s:Number($('duration').value)}:{};button.disabled=true;
    try{const result=await api(`/api/buses/${selected}/commands`,{method:'POST',body:JSON.stringify({target:button.dataset.target||'sensor',action,params})});text('command-result',`${labels[result.status]} · ${actionNames[action]||action}`);await refreshCommands();}catch(e){showError(e);}finally{button.disabled=false;}
  };});
  for(const bus of await api('/api/buses'))addBus(bus);await loadBus();
  let connectedBefore=false;connect(receive,online=>{text('connection',online?'Đã kết nối trực tiếp':'Mất kết nối · đang thử lại');$('connection').className=`pill ${online?'online':''}`;if(online&&connectedBefore)loadBus().catch(showError);if(online)connectedBefore=true;});
  setInterval(()=>{renderAges();beep();},1000);
}
$('logout').onclick=logout;$('bus').onchange=()=>loadBus().catch(showError);$('refresh-alerts').onclick=()=>refreshAlerts().catch(showError);$('refresh-audit').onclick=refreshAudit;
$('audit-tab').onclick=()=>{$('overview').hidden=true;$('audit-panel').hidden=false;$('audit-tab').classList.add('selected');$('overview-tab').classList.remove('selected');refreshAudit();};
$('overview-tab').onclick=()=>{$('overview').hidden=false;$('audit-panel').hidden=true;$('audit-tab').classList.remove('selected');$('overview-tab').classList.add('selected');drawChart();};
$('sound').onclick=async()=>{try{audio??=new (window.AudioContext||window.webkitAudioContext)();await audio.resume();sound=!sound;text('sound-label',sound?'Tắt âm cảnh báo':'Bật âm cảnh báo');$('sound').setAttribute('aria-pressed',String(sound));}catch(e){showError(new Error('Trình duyệt không hỗ trợ âm báo.'));}};
window.addEventListener('resize',drawChart);init().catch(showError);
