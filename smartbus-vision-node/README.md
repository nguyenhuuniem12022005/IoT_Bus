# Smartbus Vision Node — Task 3

## 1. Giới thiệu

Laptop xử lý YOLOv8 tại xe, gửi số người độc lập và chỉ phát video khi có người xem Dashboard.
Luồng: camera (thread giữ khung mới nhất) → YOLOv8 person → ROI → trung vị và xác nhận liên tiếp → MQTT. Không tích luỹ khung cũ hoặc số đếm khi mất mạng.

## 2. Yêu cầu

Python 3.10–3.12, webcam (hoặc video/RTSP), ít nhất 4 GB RAM. `ultralytics` kéo theo PyTorch; bản CPU là đủ. Với GPU NVIDIA, có thể cài PyTorch CUDA theo [hướng dẫn chính thức](https://pytorch.org/get-started/locally/) **trước** khi cài requirements. Lần chạy YOLO đầu cần mạng để tải `models/yolov8n.pt`; test không tải model và không cần GPU.

## 3. Cài đặt

Mở terminal trong thư mục `smartbus-vision-node`, rồi chạy:

```bash
python -m venv .venv
# Windows PowerShell : .\.venv\Scripts\Activate.ps1
#   (nếu bị chặn quyền: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass)
# Windows CMD        : .venv\Scripts\activate.bat
# Linux / macOS      : source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
# Thoát môi trường ảo khi xong: deactivate
```

Kích hoạt bằng lệnh tương ứng hệ điều hành (bỏ ký tự `#` trước lệnh đó). Sao chép `.env.example` thành `.env`: PowerShell `Copy-Item .env.example .env`, Linux/macOS `cp .env.example .env`. Điền tài khoản riêng của node; không đưa `.env` lên Git. Không cần tạo `.env` khi dùng `--no-mqtt`.

## 4. Cấu hình

Thứ tự ưu tiên: YAML < `.env` < biến môi trường tiến trình < CLI. Đường dẫn YAML mặc định, model tương đối và thư mục logs tính từ thư mục dự án; đường dẫn nguồn video và `--config` tường minh tính từ thư mục làm việc hiện tại. Dùng đường dẫn tuyệt đối khi chạy nền.

| Khoá YAML | Ý nghĩa |
|---|---|
| `bus_id` | Xe, mặc định `bus01`; chỉ chữ, số, `-`, `_` |
| `source` | Webcam `0`, đường dẫn video hoặc URL RTSP |
| `loop_video` | Tua lại video khi hết, mặc định true |
| `frame_width`, `frame_height` | Kích thước webcam yêu cầu, 640×480; driver có thể chọn khác |
| `infer_fps` | Giới hạn suy luận, mặc định 5 lần/s |
| `model.path` | Model YOLOv8, mặc định `models/yolov8n.pt` |
| `model.conf`, `model.iou` | Ngưỡng độ tin cậy .40 và loại hộp trùng .50 |
| `model.imgsz` | Kích thước suy luận 640 |
| `model.device` | `auto` chọn CUDA nếu có, `cpu`, hoặc `cuda:0` |
| `roi` | Danh sách đỉnh chuẩn hoá [x,y] trong [0,1], rỗng dùng toàn ảnh |
| `counter.window` | Số mẫu trung vị, mặc định 5 |
| `counter.min_change_frames` | Xác nhận ứng viên liên tiếp, mặc định 2 |
| `publish.count_interval_s` | Gửi mỗi 1 s khi có kết quả mới, hoặc ngay khi số đổi |
| `publish.status_interval_s` | Gửi trạng thái mỗi 10 s và khi camera/paused đổi |
| `stream` | FPS, kích thước, chất lượng, giới hạn JPEG, hộp nhận diện và lease; xem phần video bên dưới |
| `preview` | Mặc định false, không mở cửa sổ |

| Biến môi trường | Ý nghĩa |
|---|---|
| `BUS_ID` | Ghi đè `bus_id` |
| `MQTT_HOST` | Broker, mặc định localhost |
| `MQTT_PORT` | Dev 1883; nếu bỏ trống và TLS=true thì 8883 |
| `MQTT_TLS` | `true` bật xác minh TLS bằng CA hệ thống; `false` dùng dev |
| `MQTT_USERNAME` | Phải trùng client ID `laptop-{bus_id}`; tự suy ra nếu không đặt |
| `MQTT_PASSWORD` | Mật khẩu MQTT riêng node |
| `VISION_SOURCE` | Ghi đè source; rỗng thì giữ YAML |
| `LOG_LEVEL` | DEBUG, INFO, WARNING, ERROR, CRITICAL |

`.env.example` đặt cổng dev 1883: khi bật TLS nhớ đổi sang 8883. Tài khoản chỉ được publish `vision/#`, `cmd/ack` và subscribe duy nhất `cmd/vision` trong xe của mình. MQTT 3.1.1, không tắt kiểm tra chứng chỉ. Đối chiếu API tại [Paho client](https://eclipse.dev/paho/files/paho.mqtt.python/html/client.html) và [Ultralytics predict](https://docs.ultralytics.com/modes/predict/).

## 5. Chạy

```bash
python -m vision_node.main --source 0
```

Các tuỳ chọn: `--source`, `--bus-id`, `--config`, `--no-mqtt`, `--preview`, `--max-frames N` (số khung đã suy luận). Mặc định headless; `q` thoát preview, Ctrl+C/SIGTERM gửi trạng thái offline rồi giải phóng tài nguyên. Log ra console và `logs/vision_node.log` xoay vòng 2 MB × 3 bản dự phòng. Với `--no-mqtt`, mỗi lần đủ chu kỳ hoặc số đổi sẽ log payload đếm.

## 6. Chạy không có camera hoặc model

```bash
python -m vision_node.main --no-mqtt --source duong_dan_video.mp4 --max-frames 100
```

Không có model: chạy `pytest -q`, các test dùng `FakeDetector([0,0,2,2,...])`, `FakeCamera` và `FakePublisher`. Có thể import `VisionPipeline` và ba đối tượng giả như trong `tests/test_pipeline.py` để thay kịch bản. CLI dịch vụ thật luôn dùng YOLO, không thay số đếm thật bằng số giả.

## 7. Kiểm thử một mình

```bash
pytest -q
python scripts/mock_subscriber.py
```

Test kiểm tra schema, count/ROI, camera phục hồi, MQTT, lease, FPS, giới hạn JPEG và PAUSE/RESUME bằng dữ liệu trong RAM. Mock gửi lệnh STREAM_START/STOP và in kích thước khung, không ghi ảnh.

## 8. Hiệu năng

```bash
python scripts/benchmark_model.py --source video.mp4 --frames 100
```

In FPS suy luận trung bình (không tính warm-up), FPS toàn luồng và p95 thời gian detect; mặc định timeout 120 s. Mục tiêu ≥3 FPS CPU với yolov8n/imgsz=640 là mục tiêu cần đo trên máy thật, không phải cam kết. Hạ imgsz xuống 480/320 nếu chậm; giảm infer_fps để giảm tải; dùng cuda:0 nếu PyTorch hỗ trợ GPU. Vòng suy luận chỉ lấy khung gần nhất; file video chạy theo FPS nguồn để không đọc hết tệp ngay lập tức.

## 9. Đặt camera và ROI

Đặt camera cao, cố định, nhìn được ghế và lối đi, tránh ngược sáng/chói qua cửa sổ. Đo các đỉnh vùng khoang xe trên ảnh: chia x cho chiều rộng, y cho chiều cao. Nhập theo thứ tự quanh đa giác, không tự cắt, ví dụ `roi: [[0.05,0.1],[0.95,0.1],[0.95,0.95],[0.05,0.95]]`. Chỉ giữ người có tâm bbox nằm trong hoặc trên biên ROI. Khi bật `crossing`, đặt camera nhìn cửa để đếm lượt lên/xuống. IR trên ESP32 tiếp tục đếm độc lập. Kiểm tra thực tế người bị che, ánh sáng yếu, ghế trống và người ngoài cửa sổ trước khi dùng số đếm làm bằng chứng.

## 10. Chạy dịch vụ nền

Windows Task Scheduler: tạo tác vụ lúc đăng nhập; Program là đường dẫn tuyệt đối `.venv\Scripts\python.exe`; Arguments `-m vision_node.main`; Start in là thư mục `smartbus-vision-node`. Bật khởi động lại khi thất bại, bảo đảm tài khoản tác vụ được phép truy cập webcam. Bỏ `--preview` để chạy headless. Tắt sleep nếu cần chạy liên tục.

Ví dụ systemd (chỉ minh hoạ trong README, thay đường dẫn/tài khoản):

```ini
[Unit]
Description=Smartbus vision node
After=network.target

[Service]
Type=simple
User=smartbus
WorkingDirectory=/opt/smartbus-vision-node
ExecStart=/opt/smartbus-vision-node/.venv/bin/python -m vision_node.main
Restart=on-failure
RestartSec=5
TimeoutStopSec=15
SupplementaryGroups=video

[Install]
WantedBy=multi-user.target
```

Sau khi quản trị viên đặt unit, dùng `systemctl enable --now smartbus-vision`, xem `journalctl -u smartbus-vision`. Node vẫn đếm khi mạng chưa sẵn sàng.

## 11. Quyền riêng tư

Không ghi ảnh/video ra đĩa; khung chỉ nằm trong RAM. Log không chứa ảnh, mật khẩu hoặc URL nguồn. Dùng TLS và ACL riêng cho từng node.

## 12. Cấu trúc thư mục

```text
smartbus-vision-node/
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
├── pytest.ini
├── config/
│   └── config.yaml
├── models/
│   └── .gitkeep
├── logs/
│   └── .gitkeep
├── vision_node/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── camera.py
│   ├── detector.py
│   ├── counter.py
│   ├── streamer.py
│   ├── schemas.py
│   ├── mqtt_publisher.py
│   └── utils/
│       ├── __init__.py
│       └── logger.py
├── scripts/
│   ├── test_camera.py
│   ├── benchmark_model.py
│   └── mock_subscriber.py
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_counter.py
    ├── test_schemas.py
    ├── test_streamer.py
    ├── test_config.py
    └── test_pipeline.py
```

Các tệp runtime `.env`, `.venv`, model, log và bytecode nằm trong quy tắc bỏ qua Git; không phải tệp nguồn bổ sung.

## 13. Tích hợp Task 1 và 2

Mọi topic có tiền tố `smartbus/{bus_id}/`, ts là epoch milliseconds UTC.

| Topic đuôi | Hướng node laptop | QoS | Retain |
|---|---|---|---|
| `vision/frame` | Publish | 0 | false |
| `vision/count` | Publish | 0 | false |
| `vision/status` | Publish | 1 | true |
| `cmd/ack` | Publish | 1 | false |
| `cmd/vision` | Subscribe duy nhất | 1 | false |

LWT chính xác `{"bus_id":"bus01","node":"vision","online":false}`. Status đầy đủ gửi khi kết nối/đổi trạng thái/10 s. ESP32 chỉ nghe count như đầu vào tuỳ chọn, Web nhận độc lập cả sensor và vision. Không import mã của Task 1/2. Nên bật broker → mock/Web → laptop/ESP32 để dễ quan sát; các node không đợi nhau và có thể bật theo thứ tự bất kỳ.

Đổi `BUS_ID` cho cả hệ thống và `MQTT_USERNAME=laptop-<bus_id>` cùng mật khẩu/ACL tương ứng. `--bus-id` ghi đè BUS_ID nhưng vẫn kiểm tra username phải khớp. Lệnh phải đủ `cmd_id, ts, action, params, issued_by`; params={} hoặc {fps: N} cho STREAM_START. Nhớ 32 cmd_id gần nhất, không thực hiện lại nhưng trả lại ACK của lệnh trùng trong cửa sổ đó. Lệnh lỗi có cmd_id hợp lệ trả ack=false; JSON hỏng hoặc thiếu cmd_id chỉ ghi log vì không thể gắn ack với lệnh nào. Lệnh retained bị bỏ để tránh thực thi lệnh cũ sau reconnect.

## 14. Xử lý sự cố và giả định

- Camera không mở: đóng ứng dụng đang giữ webcam, kiểm tra quyền Camera của Windows, thử `--source 1`, kiểm tra RTSP và firewall. Driver webcam Windows dùng DirectShow. RTSP có timeout mở/đọc 2 s; một số driver webcam có thể chặn lâu hơn và không hỗ trợ huỷ từ Python.
- MQTT bị từ chối: xem reason code, kiểm tra host/cổng/TLS, username=client_id, mật khẩu và ACL. Không dùng tài khoản laptop cho mock Backend. Nếu không thấy count, kiểm tra camera_ok và paused.
- FPS thấp: giảm imgsz hoặc infer_fps, kiểm tra CPU đang bận và bản PyTorch. Không tải lại model trong vòng lặp.
- Không tải model: kiểm tra mạng, tải `yolov8n.pt` từ nguồn Ultralytics tin cậy rồi đặt trong models, hoặc chỉ chạy test giả. Lỗi model lúc khởi động được báo ra terminal; không giả lập kết quả để che lỗi.
- Nhịp count phụ thuộc có kết quả suy luận mới: không phát lại số cũ nếu mất camera, pause hay suy luận lỗi. `--max-frames` đếm khung suy luận thành công; nguồn lỗi sẽ tiếp tục phục hồi cho tới Ctrl+C. File `loop_video=false` kết thúc dịch vụ khi hết tệp.
- Bộ nhớ lệnh là cửa sổ 32 cmd_id trong tiến trình, không lưu qua restart. Hàng đợi lệnh tối đa 64; lệnh quá 16 KiB hoặc quá tải bị bỏ và ghi log.

Trước nghiệm thu phần cứng, cần đo FPS và chạy với webcam, broker thật, lệnh từ mock, rút/gắn camera và Ctrl+C. Test giả không chứng minh các phép thử phần cứng đó đã đạt.

## MJPEG nội bộ tùy chọn

Tùy chọn cũ `--mjpeg` vẫn dành cho kiểm tra thủ công tại localhost:8081, có test riêng. Dashboard dùng endpoint Backend và không nhập URL laptop. Không bật endpoint nội bộ này khi triển khai công khai.

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

## Đếm sĩ số qua cửa xe (phải → trái là vào)

Cấu hình `crossing.direction: left`: đi từ phải sang trái qua hết vùng đệm thì **VÀO +1**;
chiều ngược lại **RA −1**. Vạch đứng vàng mặc định tại `line: 0.5`, hai mép đứt tại
`line ± margin`. Đặt vạch đúng giữa cửa trong ảnh. Một người chỉ đứng trong ảnh hoặc
đứng rung giữa hai mép chưa được tính là lượt vào. Hình có mũi tên hai chiều, đường đi
màu xanh dương và ID; nhãn hiển thị **Còn trên xe / Vào / Ra / Thấy** trên cả Dashboard
và preview. `Thấy` là số người YOLO nhìn thấy lúc đó, khác sĩ số tích luỹ trên xe.

`vision/count.person_count` gửi sĩ số còn lại, `raw_count` gửi số người đang nhìn thấy.
Người đi khuất khỏi camera không tự làm giảm sĩ số. Tạm dừng/mất camera chỉ xoá dấu theo dõi,
không xoá sĩ số. Lượt ra được chặn ở 0 để không âm. `initial_count` là sĩ số lúc khởi động;
đặt đúng nếu xe không trống. Bộ đếm và lượt vào/ra hiện chỉ ở RAM, khởi động lại sẽ lấy
`initial_count`; không tự khôi phục sĩ số chuyến trước. Không thể suy ra các lượt đi qua
khi camera bị mất hoặc tạm dừng.

Ghép người dùng chuyển động tâm dự đoán, `max_distance: 0.35` và `max_missed: 5`.
Với người chen lấn, che nhau lâu hoặc FPS thấp, ID vẫn có thể nhầm: cần kiểm thử tại cửa
thật và điều chỉnh vị trí camera/vạch, ROI, ánh sáng. Nếu `Thấy: 0` dù có người, kiểm tra
model, vùng ROI và ngưỡng `model.conf`; vạch đếm không thể bù cho việc YOLO không nhận diện.
Sau khi đổi cấu hình/mã nguồn cần khởi động lại tiến trình node vision.
