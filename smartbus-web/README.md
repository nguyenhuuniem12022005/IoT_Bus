# SmartBus Web — Trung tâm giám sát an toàn hành khách

## 1. Giới thiệu

Task 1 gồm FastAPI, cầu nối MQTT, MongoDB, JWT/RBAC, Audit Log, WebSocket và Dashboard tiếng Việt. ESP32 (Task 2) và laptop camera (Task 3) kết nối broker độc lập. Web không import mã nguồn của hai task còn lại và **không tự tạo cảnh báo**. Chỉ topic `alert` từ ESP32 tạo/nâng mức/đóng cảnh báo. Xác nhận đã xử lý trên Web chỉ ghi nhận người xử lý, không tắt còi; muốn tắt chu kỳ cần lệnh `ALARM_RESET` hoặc Safety trên xe.

## 2. Yêu cầu hệ thống

- Python **3.11**; Docker Compose tùy chọn để chạy MongoDB 7 và Mosquitto 2.
- MongoDB local hoặc Atlas và broker MQTT 3.1.1; production dùng TLS cổng 8883.
- Trình duyệt hiện đại hỗ trợ WebSocket, Canvas, Web Audio. Không cần CDN, thư viện biểu đồ hay phần cứng để kiểm thử tự động.
- Chạy tất cả lệnh dưới đây từ thư mục `smartbus-web/`.

## 3. Cài đặt

```bash
python -m venv .venv
# Windows PowerShell : .\.venv\Scripts\Activate.ps1
#   (nếu bị chặn quyền: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass)
Windows CMD        : .venv\Scripts\activate.bat
Linux / macOS      : source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
# Thoát môi trường ảo khi xong: deactivate
```

Sao chép `.env.example` thành `.env` (`Copy-Item .env.example .env` trên PowerShell hoặc `cp .env.example .env` trên Linux). Đặt mật khẩu riêng trước khi dùng ngoài môi trường demo. `.env` đã được bỏ qua bởi Git.

## 4. Cấu hình `.env`

| Khóa | Ý nghĩa / mặc định |
|---|---|
| `APP_ENV` | `dev`; dùng `production` để bắt buộc TLS và bí mật riêng |
| `PORT` | Cổng HTTP dự kiến, `8000`; truyền `--port` cho Uvicorn khi đổi |
| `MONGODB_URI` | URI MongoDB, `mongodb://localhost:27017`; Atlas dùng URI `mongodb+srv://...` |
| `MONGODB_DB` | Tên database `smartbus` |
| `MQTT_HOST` | Host broker `localhost`, không có tiền tố `mqtt://` |
| `MQTT_PORT` | Dev `1883`; production `8883` |
| `MQTT_TLS` | `false` ở dev; `true` bật xác minh chứng chỉ CA hệ thống |
| `MQTT_USERNAME` | Tài khoản Web `backend` |
| `MQTT_PASSWORD` | Mật khẩu broker; giá trị mẫu `change-me` phải thay |
| `MQTT_CLIENT_ID` | `backend-smartbus`, giữ duy nhất cho tiến trình Web |
| `DEFAULT_BUS_IDS` | Danh sách xe phân cách dấu phẩy, mặc định `bus01` |
| `JWT_SECRET` | Khóa ký HS256; production tối thiểu 32 ký tự ngẫu nhiên |
| `JWT_EXPIRE_MINUTES` | Thời hạn JWT, `60` phút |
| `CORS_ORIGINS` | Danh sách origin phân cách dấu phẩy; dev `*`; production đặt đúng HTTPS origin |
| `SEED_ADMIN_USERNAME` / `SEED_ADMIN_PASSWORD` | Tài khoản admin ban đầu, username `admin` |
| `SEED_OPERATOR_USERNAME` / `SEED_OPERATOR_PASSWORD` | Tài khoản điều hành ban đầu, username `operator1` |
| `SEED_VIEWER_USERNAME` / `SEED_VIEWER_PASSWORD` | Tài khoản quan sát ban đầu, username `viewer1` |
| `TELEMETRY_TTL_DAYS` | Giữ telemetry, events, vision_counts `7` ngày bằng BSON datetime `received_at` |
| `NODE_OFFLINE_AFTER_S` | Quá `10` giây không có telemetry/count thì node đó offline |
| `COMMAND_TIMEOUT_S` | Quá `10` giây không có ACK thì lệnh TIMEOUT |
| `VIDEO_RENEW_S` | Gia hạn video mỗi 15 giây; phải nhỏ hơn lease 30 giây |
| `VIDEO_STOP_GRACE_S` | Chờ 5 giây sau người xem cuối |
| `VIDEO_MAX_VIEWERS` | Tối đa 5 kết nối mỗi xe |
| `VISION_STALE_S` | Count camera nhận trong `10` giây mới được coi là tươi |

Mật khẩu seed mẫu đều là `change-me`. Script seed chỉ thêm người dùng thiếu, không thay mật khẩu hay quyền tài khoản hiện hữu. Khi Web khởi động, seed tự động chỉ chạy nếu collection users rỗng. Đổi mật khẩu seed trong `.env` không đổi mật khẩu đã lưu trong MongoDB.

## 5. Chạy dev

```bash
docker compose -f infra/docker-compose.yml up -d
uvicorn app.main:app --reload
```

Mở [Dashboard local](http://localhost:8000), đăng nhập bằng tài khoản đã cấu hình. API công khai [health](http://localhost:8000/api/health) trả `{status:"ok", mongo:bool, mqtt:bool, time:ms}`. `status=ok` phản ánh HTTP còn sống; luôn kiểm tra riêng `mongo` và `mqtt`. Khi Mongo chưa sẵn sàng, tác vụ khởi tạo tự thử lại với backoff, API cần dữ liệu trả 503. MQTT chỉ bắt đầu sau khi Mongo/chỉ mục/seed/khôi phục trạng thái hoàn tất. MQTT tự nối lại với backoff 1–60 giây; Mongo driver tự khôi phục kết nối, tác vụ nền thử lại tối đa mỗi 30 giây.

Chỉ chạy **một worker/instance**: trạng thái, ảnh gần nhất và WebSocket nằm trong bộ nhớ. Không bật `--workers` nhiều hơn 1. Mỗi xe có khóa asyncio riêng; cập nhật dùng Mongo `$set` theo trường, không thay cả tài liệu. Khởi động lại Web phục hồi số đếm/lịch sử nhưng đánh dấu hai node offline cho tới khi nhận dữ liệu mới. Ảnh chỉ nằm trong RAM và mất khi Web khởi động lại.

## 6. Demo không phần cứng

```bash
python scripts/simulate_devices.py --scenario forgotten_child
```

Hai client riêng `esp32-bus01` và `laptop-bus01` chạy ở hai thread, mỗi client có vòng MQTT riêng. Có thể chạy hai terminal độc lập:

```bash
# Terminal 1
python scripts/simulate_devices.py --bus bus01 --node sensor --scenario forgotten_child
# Terminal 2
python scripts/simulate_devices.py --bus bus01 --node vision --scenario forgotten_child
```

Không chạy đồng thời `--node both` và node riêng cùng bus vì sẽ trùng client_id. Dừng bằng Ctrl+C để gửi status offline; mất tiến trình đột ngột sử dụng LWT. Tắt một node chỉ đổi trạng thái node đó; mỗi thẻ hiển thị thời gian cập nhật riêng.

| Kịch bản | Quan sát dự kiến ở tốc độ 1.0 |
|---|---|
| `normal` | Bật máy tại giây 1, 5 BOARD/2 ALIGHT, tắt máy tại giây 10, Safety tại giây 15; SAFE dù IR còn 3; không alert |
| `forgotten_child` | Tắt máy tại giây 10; IR còn 1 và PIR chuyển động; WARNING khoảng giây 40, CRITICAL và quạt tự bật khoảng giây 70; gửi ALARM_RESET để kết thúc chu kỳ |
| `false_alarm` | IR/PIR/camera đều không thấy người; giây 40 vẫn CHECKING, còi tắt, không alert; Safety giây 50 chuyển SAFE |
| `camera_only` | IR=0, không PIR, camera=1; WARNING khoảng giây 40 với VISION_PERSON_DETECTED; Safety giây 55 đóng alert, camera vẫn thấy người |

`--node sensor|vision|both` mặc định `both`. `--speed 1.0` mặc định; có thể dùng `--speed 5` để tăng tốc đồng hồ simulator. **Cả hai terminal phải dùng cùng speed**. Tốc độ này rút ngắn cả chu kỳ gửi và thời hạn máy trạng thái mô phỏng; thời hạn Web vẫn theo thời gian thực. `camera_only --node sensor` không có camera khác thì không cảnh báo; `--node vision` chỉ hiển thị thông tin, không có alert.


## 7. Kiểm thử

```bash
pytest -q
```

Tests dùng FakeDB và FakeBridge, không cần Mongo/MQTT, không khởi động firmware hoặc YOLO. Có kiểm tra 400 bản tin xen kẽ bằng `asyncio.gather`, hai xe độc lập, JWT/RBAC, vòng đời cảnh báo, ACK trùng/sai node, timeout, payload lỗi, status LWT, TTL, WebSocket 4401 và máy trạng thái simulator.

Kiểm thử tích hợp thủ công: chạy hạ tầng + Web + simulator, đợi WARNING/CRITICAL, kiểm tra banner/quạt, gửi ALARM_RESET và xem lệnh ACKED_OK, alert CLOSED cùng Audit Log. Với hai terminal riêng, dừng lần lượt sensor và vision rồi kiểm tra hai dấu online độc lập. Chạy false_alarm và camera_only bằng bus riêng hoặc dọn kịch bản cũ để tránh nhầm cảnh báo trước đó. Không dùng tài khoản viewer để thử điều khiển: server trả 403.

## 8. Triển khai Render + Atlas + broker TLS

1. Tạo MongoDB Atlas cluster, database user riêng và URI. Cấu hình Network Access cho dải IP outbound của dịch vụ Render theo thông tin trong tài khoản; nếu dùng mạng mở tạm để demo, thu hẹp lại sau thử nghiệm.
2. Tạo broker cloud có MQTT 3.1.1/TLS cổng 8883 và chứng chỉ CA tin cậy. Tạo ba tài khoản theo bảng định danh, cấu hình ACL tách biệt. `acl.conf` là mẫu cho Mosquitto, cần chuyển quyền tương đương sang giao diện broker cloud.
3. Đẩy repository chứa thư mục `smartbus-web` lên kho Git của bạn. Tạo Render Blueprint từ `smartbus-web/render.yaml`. `rootDir: smartbus-web` giả định repo cha; nếu chỉ đẩy riêng nội dung thư mục này, xóa `rootDir` trong cấu hình triển khai.
4. Nhập mọi biến `sync: false`: Mongo URI, broker host/password, JWT secret, ba mật khẩu seed và origin HTTPS. Chọn `MQTT_TLS=true`, `MQTT_PORT=8883`, `APP_ENV=production`. Không commit bí mật.
5. Build `pip install -r requirements.txt`; Start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`; Python `3.11.9`; health `/api/health`.
6. Kiểm tra health mongo/mqtt true, đăng nhập qua HTTPS, kết nối WSS và gửi thử FAN_ON. Chỉ chạy một instance/worker, tránh trùng MQTT client ID.
7. Gói free có thể ngủ: WebSocket ngắt, Web không nhận MQTT trong thời gian ngủ; khi thức dậy sẽ kết nối lại và các node tiếp tục gửi dữ liệu mới. Không coi Web trên gói ngủ là nơi lưu đủ mọi sự kiện khi vắng mặt; ESP32 vẫn tự báo động cục bộ. Để giám sát liên tục dùng dịch vụ luôn hoạt động.

Mosquitto dev chỉ mở localhost, `allow_anonymous true`. Để bật xác thực: tạo password_file bằng `mosquitto_passwd`, mount vào container, đặt `allow_anonymous false`, bỏ comment `password_file`/`acl_file`, thêm listener TLS và chứng chỉ phù hợp nếu đưa broker ra ngoài. Tạo tài khoản `esp32-bus01`, `laptop-bus01`, `backend`; mẫu ACL không cho node khác đọc/ghi chéo xe. Nhân bản nhóm quyền khi thêm bus.

## 9. Cấu trúc thư mục và giao diện

```
smartbus-web/
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
├── render.yaml
├── infra/
│   ├── docker-compose.yml          # Mosquitto + MongoDB cho môi trường dev
│   └── mosquitto/
│       ├── mosquitto.conf
│       └── acl.conf                # ACL theo bảng định danh ở mục 3.1
├── app/
│   ├── __init__.py
│   ├── main.py                     # tạo FastAPI app, lifespan (Mongo, MQTT, tác vụ nền), mount static
│   ├── config.py                   # pydantic-settings đọc .env
│   ├── database.py                 # kết nối Motor, tạo chỉ mục, get_db()
│   ├── models/
│   │   ├── __init__.py
│   │   └── schemas.py              # pydantic models: payload hợp đồng + request/response REST
│   ├── core/
│   │   ├── __init__.py
│   │   ├── security.py             # bcrypt, JWT, dependency RBAC
│   │   └── logging.py              # cấu hình logging
│   ├── mqtt_bridge/
│   │   ├── __init__.py
│   │   ├── client.py               # paho-mqtt 2.x, TLS, reconnect, cầu nối thread → asyncio
│   │   └── handlers.py             # xử lý từng topic nhận được
│   ├── services/
│   │   ├── __init__.py
│   │   ├── state_service.py        # bus_state, count_mismatch, phát hiện offline
│   │   ├── alert_service.py        # upsert alert, ack
│   │   ├── command_service.py      # tạo lệnh, publish, theo dõi ack/timeout
│   │   ├── audit_service.py        # ghi/đọc audit
│   │   └── ws_manager.py           # quản lý kết nối WebSocket, broadcast
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── buses.py
│   │   ├── alerts.py
│   │   ├── commands.py
│   │   ├── audit.py
│   │   ├── health.py
│   │   └── ws.py
│   └── static/
│       ├── index.html
│       ├── login.html
│       ├── css/
│       │   └── style.css
│       └── js/
│           ├── api.js
│           ├── ws.js
│           ├── dashboard.js
│           └── login.js
├── scripts/
│   ├── seed_users.py               # tạo admin/operator/viewer từ .env (idempotent)
│   └── simulate_devices.py         # giả lập ESP32 + Laptop (mục 3.7)
└── tests/
    ├── __init__.py
    ├── conftest.py                 # FakeDB trong bộ nhớ + client test, KHÔNG cần Mongo/MQTT thật
    ├── test_auth.py
    ├── test_mqtt_handlers.py
    ├── test_commands.py
    ├── test_concurrent_nodes.py    # sensor + vision gửi xen kẽ/đồng thời, không mất/ghi đè dữ liệu
    └── test_api.py
```

| Method |Đường dẫn | Quyền | Mô tả |
|---|---|---|---|
| POST | `/api/auth/login` | công khai | Body `{username,password}` → `{access_token,token_type:"bearer",username,role,expires_in}` |
| GET | `/api/auth/me` | đã đăng nhập | `{username,role}` |
| GET | `/api/health` | công khai | `{status:"ok",mongo:bool,mqtt:bool,time:ms}` |
| GET | `/api/buses` | viewer+ | Danh sách `bus_state` của mọi xe |
| GET | `/api/buses/{bus_id}/state` | viewer+ | `bus_state` hiện tại |
| GET | `/api/buses/{bus_id}/history?minutes=60&limit=500` | viewer+ | Mảng `{ts,ir_count,vision_count,state}` tăng dần theo `ts` |
| GET | `/api/buses/{bus_id}/events?limit=100` | viewer+ | Sự kiện mới nhất trước |
| POST | `/api/buses/{bus_id}/video-session` | viewer+ | Cấp cookie HttpOnly cho thẻ img |
| GET | `/api/buses/{bus_id}/stream.mjpg` | viewer+ | HTTP MJPEG, tối đa 5 người xem/xe |
| GET | `/api/alerts?bus_id=&status=&limit=50` | viewer+ | Danh sách cảnh báo |
| POST | `/api/alerts/{alert_id}/ack` | operator+ | Body `{note?}`; ghi `acknowledged_by/at` |
| POST | `/api/buses/{bus_id}/commands` | operator+ | Body `{target:"sensor"\|"vision",action,params?}` → **202** `{cmd_id,status:"SENT"}`. Kiểm tra `action` thuộc enum của `target`; sai → 422; `PAUSE`/`RESUME` yêu cầu admin → 403 nếu không đủ quyền |
| GET | `/api/commands?bus_id=&limit=50` | viewer+ | Lịch sử lệnh |
| GET | `/api/audit-logs?limit=100&actor=&action=` | admin | Audit Log |
| WS | `/ws?token=<JWT>` | đã đăng nhập | Token sai/hết hạn → đóng với mã 4401 |

JWT dùng `Authorization: Bearer <access_token>`; WebSocket `/ws?token=<JWT>`. Static, login, health công khai; các route còn lại yêu cầu xác thực. Viewer chỉ xem; operator điều khiển và xác nhận cảnh báo; admin thêm PAUSE/RESUME và Audit. Không có API công khai trả password_hash. JWT được giữ trong sessionStorage của tab; logout xóa token. Access log Uvicorn bị tắt; bộ lọc che JWT cả trong error log bắt tay WebSocket và các log qua root handler.


WebSocket gửi state ban đầu và các loại state, event, alert, vision, cmd_ack, node_status, video_frame. Reconnect sẽ nạp lại lịch sử.

`vision` mang payload vision/count; `state` mang bus_state; `node_status` chỉ có sensor_online/vision_online. `cmd_ack` mang ACK gốc và trường `status` để hiển thị vòng đời; SENT/TIMEOUT chưa có ACK nên chỉ mang `cmd_id,status`. Đây là cách giải quyết yêu cầu vừa phải gửi payload ACK vừa phải thông báo mọi chuyển trạng thái. Trường `sensor_updated_at`/`vision_updated_at` bổ sung cho bus_state hỗ trợ hai đồng hồ giao diện; không thay đổi payload MQTT. `vision_fresh` từ ESP32 bị bỏ qua; Web dùng thời gian nhận count riêng.

Lệnh được lưu SENT trước khi publish, QoS 1 không retain, chờ ACK đúng bus/node/cmd_id. ACK trễ sau TIMEOUT hoặc ACK trùng không đổi trạng thái đã kết thúc. Khi broker đang mất, Web vẫn chấp nhận lệnh và cho TIMEOUT, không chủ động xếp hàng lệnh mới để tránh điều khiển muộn. MQTT QoS 1 vốn có thể gửi lại bản đã phát nhưng chưa được broker xác nhận; thiết bị phải chống lặp cmd_id như hợp đồng.

## 10. Tích hợp Task 2 và Task 3

| Topic (sau`smartbus/{bus_id}/`) | Hướng | QoS | Retain | Chu kỳ / thời điểm |
|---|---|---|---|---|
| `sensor/telemetry` | ESP32 → | 0 | không | mỗi 2 giây |
| `sensor/event` | ESP32 → | 1 | không | ngay khi có sự kiện |
| `sensor/status` | ESP32 → | 1 | **có** (+ LWT `online:false`) | khi kết nối / mất kết nối |
| `alert` | ESP32 → | 1 | không | khi tạo / nâng cấp / đóng cảnh báo |
| `vision/frame` | Laptop → | 0 | không | JPEG nhị phân chỉ khi có lease người xem |
| `vision/count` | Laptop → | 0 | không | mỗi 1 giây hoặc khi số người đổi |
| `vision/status` | Laptop → | 1 | **có** (+ LWT `online:false`) | khi kết nối / đổi trạng thái / mỗi 10 giây |
| `cmd/sensor` | Backend → ESP32 | 1 | không | khi người dùng ra lệnh |
| `cmd/vision` | Backend → Laptop | 1 | không | khi người dùng ra lệnh |
| `cmd/ack` | ESP32/Laptop → Backend | 1 | không | ngay sau khi xử lý lệnh |

| Tình huống |Kết quả bắt buộc |
|---|---|
| Chỉ ESP32 chạy | Đ2 chỉ lấy từ PIR/IR; ESP32 chạy đủ máy trạng thái, còi/LED/quạt và gửi dữ liệu; Web hiển thị `vision_online=false` |
| Chỉ Laptop chạy | Laptop đếm và gửi liên tục; Web hiển thị số người từ camera, `sensor_online=false`; không có còi (không có ESP32) |
| Cả hai chạy, Web có mặt | ESP32 dùng thêm camera cho Đ2; Web nhận xen kẽ cả hai luồng và hiển thị đồng thời |
| Laptop tắt giữa chừng | Sau `VISION_STALE_S` giây ESP32 bỏ camera khỏi Đ2; còi vẫn chạy theo PIR/IR |
| Web mất | Không ảnh hưởng ESP32 và Laptop (broker vẫn chuyển `vision/count` cho ESP32); chỉ không có Dashboard |
| Broker mất | ESP32 còi cục bộ theo PIR/IR và đệm sự kiện; Laptop vẫn đếm, **không đệm** số cũ, nối lại thì gửi bản mới nhất |
| Chỉ Web chạy | Web đăng nhập/xem lịch sử bình thường, hiển thị cả 2 node offline, gửi lệnh được (ack sẽ `TIMEOUT`) |

Thứ tự gợi ý: broker → Web → node, không bắt buộc giữa hai node. Đổi DEFAULT_BUS_IDS ở Web, `--bus` ở simulator và bus_id/credential trong cấu hình từng node. Topic luôn `smartbus/{bus_id}/...`; username node bằng client_id. Backend mặc định client_id `backend-smartbus` nhưng username `backend` theo `.env.example`; đây là ngoại lệ cấu hình backend so với quy ước username=client_id chung.

Luật còi ở ESP32: ignition OFF quá CHECK_GRACE_S=30, chưa Safety **và** ít nhất một nguồn PIR/IR/camera tươi thấy người. Chỉ hết hạn mà không ai thì CHECKING, không còi. Camera quá VISION_STALE_S=10 bị bỏ qua; IR/PIR vẫn hoạt động. WARNING liên tục 30 giây có người nâng CRITICAL, tự bật quạt 300 giây (tối đa điều khiển từ xa 900). Mọi nguồn hết thấy người 10 giây thì đóng NO_PRESENCE, về CHECKING. Safety chuyển SAFE và đóng chu kỳ dù camera vẫn thấy người. Ignition ON đóng IGNITION_ON, RUNNING và tắt quạt; ALARM_RESET đóng REMOTE_RESET. BUZZER_SILENCE chỉ tắt còi tới lần nâng mức; RESET_COUNT đặt IR=0; TEST_BUZZER kêu một giây. Presence lấy nguyên từ telemetry, không suy luận cảnh báo trên Web.

## 11. Xử lý sự cố

| Hiện tượng | Cách kiểm tra |
|---|---|
| Mongo false / API 503 | Kiểm tra Docker Desktop đã chạy, URI, Atlas Network Access, database user và DNS; Web tự thử lại |
| MQTT false | Kiểm tra host/port, TLS, tài khoản/ACL và client_id không trùng; broker cloud dùng 8883 với CA hợp lệ |
| Một node offline | Xem terminal node đó, topic/bus_id, payload bắt buộc, LWT; quá 10 giây không count/telemetry là offline, kể cả camera PAUSE |
| Count camera cũ | Web tính freshness theo giờ nhận; không dùng ts của thiết bị hay vision_fresh trong telemetry |
| WS 4401 | JWT hết hạn/sai hoặc user không tồn tại; đăng nhập lại, kiểm tra JWT_SECRET nhất quán |
| CORS | Với frontend khác origin, thêm origin chính xác (scheme, host, port) vào CORS_ORIGINS; dashboard tích hợp không cần cross-origin |
| Render ngủ | Mở lại trang và đợi backend/broker nối lại; chọn gói luôn chạy cho giám sát liên tục |
| Lệnh TIMEOUT | Node offline, không có quyền subscribe/ACK, sai node/cmd_id hoặc chưa chạy simulator; không tự gửi lại lệnh nguy hiểm |
| Không có âm báo | Bấm Bật âm cảnh báo để trình duyệt cho phép Web Audio |
| Lịch sử không đầy đủ khi Mongo mất | Handler ghi lỗi, không có hàng đợi bền vững phía Web; số liệu chu kỳ mới tiếp tục khi khôi phục. Không đảm bảo lưu lại bản tin nhận trong thời gian mất DB |

### Giả định và giới hạn

- Cây mã nguồn giữ nguyên đặc tả; `.venv`, cache pytest/Python và file `.env` là sản phẩm môi trường chạy, không thuộc cây mã nguồn bàn giao.
- Mẫu LWT thiếu ts và các trường online được chấp nhận riêng; timestamp nhận được bổ sung phía server. Bus_state giữ số liệu gần nhất khi offline; thẻ offline và thời gian nhận cho biết độ tin cậy.
- Timestamps history là ts thiết bị (0 được thay giờ nhận), TTL dùng giờ nhận UTC. Hệ thống không tự sửa đồng hồ thiết bị sai khác 0.
- Không triển khai tự động lên Render hoặc cấp tài khoản cloud. Cần tự điền thông tin dịch vụ trước khi chạy tích hợp.

## Camera trực tiếp qua MQTT và MJPEG

Webcam → Laptop YOLOv8 → `smartbus/{bus_id}/vision/frame` (JPEG nhị phân, QoS 0, không retain)
→ Backend → `GET /api/buses/{bus_id}/stream.mjpg` → thẻ `<img>` trên Dashboard.
Video chỉ giữ trong RAM, không ghi khung hình ra đĩa. Số đếm `vision/count` và trạng thái
`vision/status` vẫn độc lập; status bổ sung `streaming: true/false`.

Người xem đầu tiên gửi `STREAM_START`; Backend gia hạn mỗi `VIDEO_RENEW_S=15` giây.
Sau khi người xem cuối đóng, chờ `VIDEO_STOP_GRACE_S=5` giây rồi gửi `STREAM_STOP`.
Laptop tự hết lease sau 30 giây không được gia hạn. Nhiều tab dùng chung một luồng MQTT;
`VIDEO_MAX_VIEWERS=5` cho mỗi xe, kết nối thứ sáu nhận HTTP 429. Mỗi người xem chỉ có
một ô khung mới nhất, khung cũ bị bỏ khi máy khách chậm. Chạy Backend với **một worker**;
muốn nhiều worker phải dùng bộ quản lý người xem dùng chung (chưa triển khai).

Node dùng `stream: {fps: 8, width: 480, height: 360, jpeg_quality: 60, max_kb: 80,
draw_boxes: true, lease_s: 30}`. FPS kẹp 1..15, giảm chất lượng JPEG đến 30;
khung vẫn quá lớn bị bỏ và ghi log, không tăng bộ đệm. Video đọc camera riêng với YOLO,
dùng hộp nhận diện gần nhất. PAUSE dừng suy luận/count và video; RESUME cho phép suy luận
trở lại, video tiếp tục khi nhận lần gia hạn kế tiếp. Mất camera không phát lại khung cũ.

Dashboard tự phát, có Tạm dừng/Tiếp tục và Toàn màn hình. Tab ẩn/rời trang đóng kết nối;
hiện lại hoặc WebSocket kết nối lại sẽ mở lại với tham số chống cache. Nhịp `video_frame`
qua WebSocket (tối đa 1 lần/giây, không chứa ảnh) giúp báo mất tín hiệu sau 3 giây.
`POST /api/buses/{bus_id}/video-session` cần Bearer, cấp cookie HttpOnly/SameSite=Strict
chỉ dùng trên đường dẫn MJPEG; JWT được kiểm tra lại trong luồng mỗi 15 giây.
Audit ghi `VIDEO_VIEW_START/STOP` với tài khoản, xe và ID kết nối. Lệnh thuê luồng
không ghi collection commands hoặc Audit, tránh làm đầy lịch sử.

ESP32 chỉ nghe `cmd/sensor` và `vision/count`, không nhận `vision/frame`.
ACL mẫu `infra/mosquitto/acl.conf` của dự án Web không cấp ESP32 quyền đọc video.
Không sửa mã ESP32. Không mở quyền wildcard `vision/#` cho tài khoản ESP32.

Thử Web (trong thư mục smartbus-web, cần MongoDB và broker theo .env):
```powershell
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
# Terminal khác:
python scripts/simulate_devices.py --node vision
python -m pytest -q
```
Mở Dashboard, đăng nhập rồi mở hai tab cùng xe. Đóng một tab vẫn xem được;
đóng tab cuối chờ khoảng 5 giây, quan sát status streaming=false. Dừng đột ngột Web,
node tự ngừng sau tối đa 30 giây. Simulator vẽ hình chữ nhật chuyển động và dấu thời gian
bằng Pillow==10.4.0 trong RAM; lease dùng thời gian thực, không bị ảnh hưởng bởi --speed.

Thử node thật (trong thư mục smartbus-vision-node):
```powershell
python -m pip install -r requirements.txt
python -m vision_node.main --source 0
python scripts/mock_subscriber.py
python -m pytest -q
```
Mock nhận JPEG nhị phân, chỉ in số byte và không lưu ảnh. Nhập STREAM_START / STREAM_STOP /
PAUSE / RESUME; STREAM_START cần gửi lại trong vòng 30 giây nếu muốn tiếp tục xem.
Không chạy mock cùng client ID với Backend thật. Kiểm tra webcam thật đạt ít nhất 5 FPS,
có hộp quanh người và dòng Người: N; đồng thời xác nhận ESP32 vẫn nhận vision/count.

Nhãn tiếng Việt dùng font hệ thống Arial (Windows), DejaVu Sans hoặc Liberation Sans (Linux).
Nếu máy Linux tối giản chưa có font, cần cài một trong các font này trước khi phát video.
