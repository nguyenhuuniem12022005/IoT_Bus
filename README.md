# SmartBus — Hướng dẫn chạy và kiểm thử

Hệ thống gồm `smartbus-web` (dashboard/API), `smartbus-sensor-node` (ESP32-S3) và `smartbus-vision-node` (camera). Cả ba phải dùng cùng broker MQTT và cùng `bus_id`, ví dụ `bus01`.

## 0. Cấu hình riêng trước khi chạy

Các giá trị dưới đây là **ví dụ**, hãy thay bằng thông tin của bạn. Mật khẩu Wi-Fi, mật khẩu MQTT và mật khẩu đăng nhập Web là ba loại khác nhau. Không cần nhập Wi-Fi của ESP32 vào Web hoặc vision: laptop dùng kết nối mạng của Windows.

### 0.1. File nào cần sửa?

| Thành phần | File | Thông tin cấu hình | Sau khi sửa |
|---|---|---|---|
| ESP32 | `smartbus-sensor-node/include/secrets.h` | Wi-Fi, mật khẩu, MQTT, mã xe | Build và nạp lại ESP32 |
| Phần cứng ESP32 | `smartbus-sensor-node/include/pins.h`, `include/config.h` | GPIO, mức kích và thời gian cảnh báo | Build và nạp lại ESP32 |
| Cổng nạp | `smartbus-sensor-node/platformio.ini` | `upload_port`, `monitor_port` | Dùng cổng mới khi nạp/monitor |
| Web | `smartbus-web/.env` | MongoDB, MQTT, JWT, tài khoản ban đầu | Khởi động lại Web |
| Vision | `smartbus-vision-node/.env` | MQTT, mã xe, nguồn camera | Khởi động lại vision |
| Nhận diện | `smartbus-vision-node/config/config.yaml` | Hướng đếm, độ phân giải, FPS, model | Khởi động lại vision |

Tạo file cấu hình lần đầu bằng PowerShell tại thư mục gốc. Các lệnh sau không ghi đè file đã có:

```powershell
if (!(Test-Path smartbus-sensor-node/include/secrets.h)) {
    Copy-Item smartbus-sensor-node/include/secrets.example.h smartbus-sensor-node/include/secrets.h
}
if (!(Test-Path smartbus-web/.env)) {
    Copy-Item smartbus-web/.env.example smartbus-web/.env
}
if (!(Test-Path smartbus-vision-node/.env)) {
    Copy-Item smartbus-vision-node/.env.example smartbus-vision-node/.env
}
```

### 0.2. Wi-Fi và MQTT trên ESP32

Mở `smartbus-sensor-node/include/secrets.h`, sửa các dòng tương ứng:

```cpp
#pragma once
#define WIFI_SSID "Ten_WiFi_cua_ban"
#define WIFI_PASS "Mat_khau_WiFi_cua_ban"
#define BUS_ID "bus01"
#define MQTT_HOST "192.168.1.10"
#define MQTT_PORT 1883
#define MQTT_USER "esp32-" BUS_ID
#define MQTT_PASS "Mat_khau_MQTT_cua_ESP32"
#define MQTT_TLS 0
#define MQTT_TLS_INSECURE 0
#define MQTT_CA_CERT ""
```

- `WIFI_SSID`: tên Wi-Fi, đúng chữ hoa/thường; dùng mạng 2,4 GHz cho ESP32-S3.
- `WIFI_PASS`: mật khẩu Wi-Fi, không phải mật khẩu Web. Trong chuỗi C++, ký tự `"` cần viết `\"`, ký tự `\` cần viết `\\`.
- `BUS_ID`: mã xe; phải khớp với vision và danh sách xe trên Web.
- `MQTT_HOST`: tên miền broker hoặc IPv4 máy chạy broker, không thêm `mqtt://`, `https://` hoặc số cổng vào đây. Ví dụ `192.168.1.10` chỉ là IP minh họa; chạy `ipconfig` trên máy broker để tìm IPv4 LAN thực tế.
- `MQTT_USER` / `MQTT_PASS`: tài khoản thiết bị được tạo trên broker. Có thể dùng username khác `esp32-bus01` nếu broker cho phép; client ID của ESP32 vẫn là `esp32-bus01`.
- Với broker local không TLS: thường dùng `MQTT_PORT 1883`, `MQTT_TLS 0`. ESP32 không dùng `localhost` để kết nối broker nằm trên laptop.

**Nếu dùng broker cloud TLS:** điền hostname do nhà cung cấp cấp, đặt `MQTT_PORT 8883`, `MQTT_TLS 1`, giữ `MQTT_TLS_INSECURE 0` và điền chứng chỉ CA PEM mà broker yêu cầu. Thay dòng `MQTT_CA_CERT` bằng mẫu sau, với nội dung chứng chỉ thật:

```cpp
#define MQTT_CA_CERT R"PEM(-----BEGIN CERTIFICATE-----
NOI_DUNG_CA_PEM_DO_NHA_CUNG_CAP_BROKER_CAP
-----END CERTIFICATE-----
)PEM"
```

Không dùng nguyên phần chữ mẫu làm chứng chỉ. ESP32 cần đồng hồ được đồng bộ để kiểm tra TLS. Web và vision bật TLS bằng `MQTT_TLS=true` và dùng kho CA của môi trường Python; file `.env` hiện không có tham số CA riêng. `MQTT_TLS_INSECURE=1` bỏ kiểm tra chứng chỉ, chỉ dành cho thử nghiệm có chủ đích, không phải cấu hình mặc định.

### 0.3. Cấu hình Web

Mở `smartbus-web/.env`. Ví dụ broker local trên cùng laptop:

```dotenv
APP_ENV=dev
PORT=8000
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB=smartbus
MQTT_HOST=localhost
MQTT_PORT=1883
MQTT_TLS=false
MQTT_USERNAME=backend
MQTT_PASSWORD='Mat_khau_MQTT_cua_backend'
MQTT_CLIENT_ID=backend-smartbus
DEFAULT_BUS_IDS=bus01
JWT_SECRET='Thay_bang_chuoi_ngau_nhien_dai_it_nhat_32_ky_tu'
SEED_ADMIN_USERNAME=admin
SEED_ADMIN_PASSWORD='Mat_khau_dang_nhap_Web_cua_ban'
SEED_OPERATOR_USERNAME=operator1
SEED_OPERATOR_PASSWORD='Mat_khau_operator_cua_ban'
SEED_VIEWER_USERNAME=viewer1
SEED_VIEWER_PASSWORD='Mat_khau_viewer_cua_ban'
```

Nếu broker ở máy khác, đổi `MQTT_HOST` thành IP/hostname broker. Nếu dùng cloud TLS, đổi host, port và TLS tương ứng như ESP32. Tài khoản backend cần quyền gửi lệnh và nhận dữ liệu/ACK. `DEFAULT_BUS_IDS` có thể là `bus01,bus02`; mỗi xe có node và client ID riêng.

`MONGODB_URI` là kết nối cơ sở dữ liệu, không phải broker. `JWT_SECRET` dùng ký phiên đăng nhập; không dùng mật khẩu Wi-Fi thay cho khóa này. Giá trị chứa khoảng trắng hoặc `#` nên đặt trong dấu nháy ở `.env`. Biến môi trường đã đặt trong terminal có thể ghi đè `.env`.

**Tài khoản seed chỉ dùng để tạo người dùng ban đầu.** Đổi `SEED_ADMIN_PASSWORD` sau khi tài khoản đã tồn tại không tự đổi mật khẩu trong MongoDB; script seed cũng không ghi đè tài khoản có sẵn. Xem `smartbus-web/docs/TAI_KHOAN_VA_NAP_CODE.md` khi cần đặt lại tài khoản. Nếu đổi `PORT`, cũng đổi `--port` trong lệnh Uvicorn và địa chỉ mở trình duyệt.

### 0.4. Cấu hình vision và video

Mở `smartbus-vision-node/.env`:

```dotenv
BUS_ID=bus01
MQTT_HOST=localhost
MQTT_PORT=1883
MQTT_TLS=false
MQTT_USERNAME=laptop-bus01
MQTT_PASSWORD='Mat_khau_MQTT_cua_vision'
VISION_SOURCE=0
LOG_LEVEL=INFO
```

Host/port/TLS phải trỏ về cùng broker với hai thành phần còn lại. Vision hiện yêu cầu username `laptop-{BUS_ID}`; ví dụ đổi xe thành `bus02` thì username là `laptop-bus02`. `VISION_SOURCE=0` chọn camera mặc định; thử `1` nếu dùng camera khác, hoặc điền đường dẫn video/URL RTSP. Để trống thì dùng `source` trong YAML. Tham số `--source` và `--bus-id` khi chạy ưu tiên hơn giá trị cấu hình tương ứng; đổi bus vẫn cần đổi username cho khớp.

Các tham số thường chỉnh trong `config/config.yaml`:

| Tham số | Ý nghĩa |
|---|---|
| `frame_width`, `frame_height` | Kích thước camera mong muốn, mặc định 640×480 |
| `infer_fps` | Giới hạn suy luận YOLO, mặc định 5; luồng video chạy riêng |
| `model.conf` | Ngưỡng nhận diện người, mặc định 0.40 |
| `crossing.direction` | Hiện đặt `left`: phải → trái là VÀO, trái → phải là RA |
| `crossing.line` | Vị trí đường đếm chuẩn hóa, mặc định 0.5 |
| `crossing.margin` | Vùng chống rung hai bên đường, mặc định 0.04; phải nhỏ hơn khoảng cách từ đường tới mép ảnh |
| `crossing.initial_count` | Sĩ số camera ban đầu, mặc định 0; khởi động lại node lấy lại giá trị này |
| `crossing.max_distance`, `crossing.max_missed` | Khoảng ghép tâm tối đa 0.35 và giữ dấu qua tối đa 5 lần mất nhận diện |
| `stream` | Video mặc định 8 FPS, 480×360, JPEG chất lượng 60, tối đa 80 KiB, lease 30 giây |
| `preview` | `true` để mở cửa sổ hình tại laptop |

Dashboard tự xem video qua Backend: **camera → YOLOv8/laptop → MQTT `vision/frame` → Backend → HTTP MJPEG → trình duyệt**. Không nhập URL laptop và không cần `--mjpeg`. Trong Web, mặc định `VIDEO_RENEW_S=15`, `VIDEO_STOP_GRACE_S=5`, `VIDEO_MAX_VIEWERS=5`. Node tự hết lease sau 30 giây không nhận gia hạn. ESP32 chỉ nghe `cmd/sensor` và `vision/count`; ACL không cấp ESP32 quyền nghe `vision/frame`.

### 0.5. Kiểm tra sau khi thay thông tin riêng

1. Lưu file, build/nạp lại ESP32 nếu sửa `secrets.h`; khởi động lại Web/vision nếu sửa cấu hình của chúng.
2. Kiểm tra Serial ESP32 có `MQTT connected`, Web `/api/health` có `mongo=true`, `mqtt=true`, và cả hai node đúng xe hiện online.
3. Gửi `TEST_BUZZER` và xem ACK; nếu TIMEOUT, kiểm tra tài khoản/ACL broker và mã xe trước khi kết luận phần cứng hỏng.
4. Mở Camera trực tiếp trên Dashboard: thấy video chuyển động, vạch/mũi tên và huy hiệu TRỰC TIẾP. Video cần cả MQTT và Backend hoạt động; số đếm vẫn gửi khi không ai xem video.

Giữ `secrets.h` và `.env` chứa thông tin thật ở máy của bạn; không đưa mật khẩu thật vào README, ảnh chụp công khai hay Git. Các file `.example` chỉ nên chứa giá trị mẫu.

## 1. Chạy Web và hạ tầng

Cần Python 3.11/3.12, Docker Desktop và PlatformIO để nạp ESP32. Mở PowerShell tại thư mục dự án:

```powershell
cd smartbus-web
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
if (!(Test-Path .env)) { Copy-Item .env.example .env }
# Điền cấu hình MongoDB, MQTT, JWT và mật khẩu seed trong .env.
docker compose -f infra/docker-compose.yml up -d
.\.venv\Scripts\python scripts/seed_users.py
.\.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

Mở [Dashboard](http://localhost:8000) và đăng nhập tài khoản admin với mật khẩu đã cấu hình. Viewer chỉ có quyền xem. Kiểm tra `/api/health`: cả `mongo` và `mqtt` phải true.

**ESP32 dùng broker trên máy tính:** cấu hình Docker mặc định chỉ mở `127.0.0.1:1883`, không truy cập được từ LAN. Trong `smartbus-web/infra/docker-compose.yml`, đổi ánh xạ thành `1883:1883`, chạy lại compose và cho phép cổng TCP 1883 qua Windows Firewall trên mạng riêng. Dùng IPv4 LAN của máy tính làm `MQTT_HOST` trên ESP32, không dùng localhost. Broker mẫu cho phép anonymous: chỉ mở trong LAN thử nghiệm tin cậy; dùng tài khoản/ACL và TLS khi triển khai. Có thể dùng broker riêng thay Docker.

## 2. Sensor và relay

Nếu chưa có, sao chép `smartbus-sensor-node/include/secrets.example.h` sang `secrets.h`. Điền Wi-Fi, broker, TLS, tài khoản và BUS_ID. Không ghi đè file cấu hình đang dùng. Client ID là `esp32-bus01`; tài khoản MQTT theo broker, không bắt buộc trùng client ID. Không chạy simulator sensor cùng lúc với ESP32 thật vì trùng ID.

```powershell
cd smartbus-sensor-node
pio run -e esp32s3
pio run -e esp32s3 -t upload --upload-port COM6
pio device monitor --port COM6 --baud 115200
```

Đổi COM6 theo máy. Đợi Serial báo `MQTT connected`, Dashboard báo sensor online. Thực hiện các thao tác phần cứng theo kịch bản tổng hợp ở mục 4.

Relay IN nối GPIO13, GND chung; cấp nguồn module đúng thông số của module. Mặc định kích mức LOW. Nếu module kích HIGH, thêm `-DSMARTBUS_RELAY_ACTIVE_LEVEL=1` vào `build_flags` của môi trường esp32s3 rồi build/nạp lại. Không đổi cực tính chỉ để thử khi chưa xác định module. Relay khởi động ở trạng thái OFF nên đèn điều khiển có thể không sáng lúc mới cấp nguồn. Đèn nguồn không sáng là vấn đề cấp nguồn cần kiểm tra riêng.

Nếu ACKED_OK, fan=true nhưng relay không hoạt động: đo GPIO13 so với GND, kiểm tra mức kích, nguồn module và dây IN. ACK chỉ xác nhận xử lý phần mềm, không xác nhận tiếp điểm relay thực sự đóng. Không có ACK: kiểm tra host/port/TLS, bus_id, quyền subscribe `smartbus/bus01/cmd/sensor` và publish `smartbus/bus01/cmd/ack`.

Các chân khác: IR1=4, IR2=6, PIR=5, ignition=7, safety=11, buzzer chủ động=12, LED RGB chung âm: R=14, G=15, B=16, SDA=8, SCL=9. Cảm biến IR/PIR là đầu vào vật lý; các lệnh Web điều khiển quạt/còi, reset cảnh báo và reset số IR, không giả lập tín hiệu cảm biến.

## 3. Camera có chiều lên/xuống

Mở terminal mới tại thư mục gốc:

```powershell
cd smartbus-vision-node
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
if (!(Test-Path .env)) { Copy-Item .env.example .env }
# Điền cùng broker/BUS_ID; username theo cấu hình vision hiện có: laptop-bus01.
.\.venv\Scripts\python -m vision_node.main --source 0 --preview
```

Trong `config/config.yaml`, cấu hình hiện tại là `crossing.direction: left`: **phải → trái là VÀO +1**, **trái → phải là RA −1**. Vạch vàng đứng tại `line: 0.5`; hai mép đứt `line ± margin` là vùng chống rung. Đặt camera nhìn cửa sao cho người lên xe đi từ phải sang trái trên ảnh, đồng thời đi qua IR1 ngoài cửa rồi IR2 trong cửa. Video có hai mũi tên, đường di chuyển và ID từng người. Nhấn Q trong preview hoặc Ctrl+C tại terminal để dừng node.

Số `Còn trên xe` là sĩ số tích luỹ; `Thấy` là số người đang được YOLO nhận diện trong khung. Người đã đi vào rồi khuất khỏi camera vẫn được tính trên xe. Pause/resume hoặc mất camera giữ sĩ số nhưng bỏ dấu theo dõi cũ. Khởi động lại node lấy `crossing.initial_count`, mặc định 0. Nút Reset sĩ số trên Web chỉ reset IR; không reset camera. Chỉ bắt đầu bài thử khi xe trống và cả hai số bằng 0.

## 4. Kịch bản kiểm thử tổng hợp: một chuyến xe và xử lý sự cố

Đây là **một bài chạy liên tục trên cùng xe `bus01`**, dùng ESP32 thật, webcam/YOLO thật, Web và cùng broker. Các chặng kế thừa sĩ số và trạng thái của chặng trước; không reset giữa các bước trừ khi được chỉ rõ. Mục 1–3 là chuẩn bị môi trường, không phải những bài kiểm thử riêng.

### 4.1. Bố trí và cách ghi nhận

- Chuẩn bị ba người đóng vai hành khách A, B, C; một người vận hành Web/đồng hồ và một người thao tác Key/Safety. Có thể kiêm nhiệm nhưng phải ghi đúng người còn ở phía trong xe.
- Người vào đi **IR1 → IR2**, đồng thời qua vạch camera **phải → trái**; người ra đi ngược lại. Đi lần lượt, để hai IR nhả hẳn trước lượt tiếp theo; mỗi cặp phải hoàn tất trong cửa sổ 1,5 giây. Không che IR bằng tay riêng trong khi hành khách đi qua camera vì sẽ tạo hai tình huống đếm khác nhau.
- Khi nói “ở trong xe”, người thử đã qua cửa và đứng bên trong, không cần luôn xuất hiện trong hình. Không đi ngang cửa ngoài các lượt được chỉ định. Nếu `Thấy: 0` ngay lúc đi qua cửa, dừng để chỉnh góc camera/ánh sáng/ROI trước khi kiểm tra hướng đếm.
- Key GPIO7 là mức giữ: nối GND là **ON**, thả là **OFF**, không phải nhấn một lần để đảo trạng thái. Safety GPIO11 nhấn nối GND. LED RGB chung âm: RUNNING xanh lá, CHECKING đỏ, WARNING/CRITICAL nháy đỏ, SAFE tắt; kênh xanh dương chưa dùng.
- Mở ba terminal tương ứng Web, Serial ESP32 và vision theo mục 1–3. Chỉ chạy một instance mỗi node; tắt simulator/fake_vision để không trùng client ID hoặc gửi số giả vào cùng xe. Web dùng một worker.
- Đăng nhập admin, chọn `bus01`. Ghi thời điểm đổi Key, sĩ số thực tế, IR, camera, trạng thái, còi/quạt, mã lệnh/ACK và mã cảnh báo. Mốc 30 giây tính theo ESP32; Dashboard có thể trễ thêm một nhịp telemetry khoảng 2 giây và thời gian mạng. Không dùng thời gian tải trang làm mốc tắt Key.
- Nếu bước trước sai sĩ số, ghi lỗi và dừng chặng: không tiếp tục với giả định sĩ số trong bảng vẫn đúng. Sửa nguyên nhân, đưa xe về trống, reset IR và khởi động lại vision với `initial_count: 0` rồi chạy lại từ đầu.

### 4.2. Chặng 1 — khởi động và đón khách

| Bước | Thao tác liên tục | Kết quả cần đạt trước bước kế tiếp |
|---|---|---|
| 1 | Xe trống, Key OFF. Khởi động hạ tầng/Web, ESP32 và vision. Mở Dashboard và đợi PIR ổn định. | `/api/health`: `mongo=true`, `mqtt=true`; hai node online; IR=0, camera=0, SAFE. Camera trực tiếp có hình chuyển động, vạch vàng, VÀO hướng trái và RA hướng phải. |
| 2 | Từ Dashboard, bấm Test còi; sau đó bật quạt thời hạn 10 giây. Chờ quạt tự tắt. | Hai lệnh ACKED_OK; còi kêu khoảng 1 giây; telemetry fan=true rồi false. Quan sát relay/quạt thật cùng thay đổi, không chỉ dựa vào ACK. Chuyến thử vẫn có 0 người. |
| 3 | Giữ Key ON. A đến gần vạch rồi dừng ở phía ngoài; A đi vào vùng đệm rồi quay lại phía ngoài, không vượt hết vùng đệm hoặc hoàn tất cặp IR. | RUNNING, LED xanh, không cảnh báo. Camera có thể `Thấy: 1` nhưng `Còn trên xe: 0`; IR=0. Không có lượt vào giả khi rung sát vạch. |
| 4 | A vào xe hoàn toàn, đứng phía trong rồi đi khuất khỏi góc camera. Sau đó B và C lần lượt vào theo cùng đường. Sau mỗi lượt chờ số ổn định. | Sĩ số thực/IR/camera lần lượt **1 → 2 → 3**. Trên video `Vào: 3`, `Ra: 0`, `Còn trên xe: 3`; `Thấy` có thể về 0. Mỗi lượt có BOARD; camera không giảm khi người khuất hình. |
| 5 | B rồi C lần lượt xuống xe qua cửa; A ở lại phía trong. | Sĩ số thực/IR/camera **3 → 2 → 1**. Video `Vào: 3`, `Ra: 2`, `Còn trên xe: 1`; có ALIGHT. Biểu đồ/lịch sử nhận cả hai nguồn, không bị video làm đứng số. |

### 4.3. Chặng 2 — kết thúc chuyến nhưng còn A trên xe

Giữ A bên trong, IR=1 và camera=1 xuyên suốt bước 6–9. **Không bấm Safety hoặc Reset cảnh báo sớm.** Số IR dương bảo đảm bằng chứng còn người không phụ thuộc PIR có bắt được A đứng yên hay không.

| Bước / mốc | Thao tác | Kết quả đồng thời trên ESP32 và Web |
|---|---|---|
| 6 — T0 | Thả Key OFF và bắt đầu bấm giờ. | CHECKING, LED đỏ, chưa có cảnh báo, còi tắt; hai sĩ số vẫn 1. |
| 7 — T0 đến trước 30 giây | Không làm gì, quan sát video và dữ liệu. | Vẫn CHECKING, không bật còi sớm. Count/status tiếp tục cập nhật. |
| 8 — khoảng T0+30 giây | Chờ WARNING. Ghi `alert_id`; bấm **Xác nhận đã xử lý** trên hàng cảnh báo với ghi chú thử nghiệm. | WARNING, LED nháy đỏ, còi ngắt quãng. Cảnh báo có SAFETY_NOT_CONFIRMED và bằng chứng IR/vision phù hợp. Xác nhận trên Web chỉ thêm người/ghi chú xử lý; trạng thái cảnh báo vẫn ACTIVE, còi vẫn hoạt động. |
| 9 — trước T0+60 giây | Bấm **Tắt còi**; giữ A trên xe và tiếp tục đợi. | Lệnh ACKED_OK; còi tắt nhưng cảnh báo vẫn ACTIVE/WARNING, không reset sĩ số và không bắt đầu lại thời hạn nâng cấp. |
| 10 — khoảng T0+60 giây | Không bấm thêm nút, chờ nâng cấp. | CRITICAL trên **cùng alert_id**, LED nháy đỏ, còi liên tục trở lại, quạt tự bật. Trạng thái người đã xác nhận trên Web vẫn còn. Kiểm tra cả relay/quạt thật và fan=true. |
| 11 | Người phụ trách kiểm tra xe rồi nhấn nút **Safety vật lý**. A vẫn ở trong để kiểm chứng thao tác không tự xoá sĩ số. | SAFE, LED tắt, còi và quạt tự động tắt. Cảnh báo CLOSED với `closed_by=SAFETY_BUTTON`. IR/camera vẫn 1; không kêu lại trong chu kỳ Key này. |
| 12 | Cho A ra xe qua cửa đúng chiều, chờ IR và camera về 0. Không tạo chuyển động PIR mới trong ít nhất 31 giây kể từ lần PIR cuối. | IR=0, camera=0; video `Vào: 3`, `Ra: 3`. Lịch sử cảnh báo và xác nhận vẫn còn; không dùng Reset sĩ số để làm giả kết quả xuống xe. |

### 4.4. Chặng 3 — kiểm tra xe trống rồi tiếp tục cùng chuyến thử

| Bước | Thao tác | Kết quả mong đợi |
|---|---|---|
| 13 | Khi xe thật sự trống, IR/camera=0 và PIR đã hết tươi: bật Key ON, đợi Dashboard RUNNING, rồi OFF. Chờ ít nhất 65 giây và không đi vào vùng PIR/cửa. | CHECKING, LED đỏ; không tạo WARNING/CRITICAL, không còi/quạt. **Không tự chuyển SAFE chỉ vì xe trống**; bấm Safety cuối bước để xác nhận về SAFE. |
| 14 | Bật Key ON. Cho A vào một lần và đứng bên trong, giữ Key ON trong các bước kiểm tra video tiếp theo. | RUNNING, IR=1, camera=1; video `Vào: 4`, `Ra: 3`. Đây là điểm bắt đầu kiểm tra truyền hình, không khởi động lại vision hoặc reset số. |
| 15 | Tạm dừng **video** bằng nút trong thẻ Camera trực tiếp, rồi tiếp tục. Sau đó thử ẩn và hiện trang. Không dùng nút Tạm dừng camera ở phần Điều khiển cho bước này. | Tạm dừng/ẩn trang đóng kết nối ảnh; nếu không còn người xem, sau khoảng 5 giây node báo `streaming=false`. Suy luận/count và trạng thái sensor vẫn chạy, sĩ số vẫn 1. Tiếp tục/hiện trang tự nối lại video; hình chuyển động và TRỰC TIẾP trở lại. |
| 16 | Mở thêm Dashboard cùng xe trong **cửa sổ thứ hai đang hiển thị**, đăng nhập nếu cần. Đóng cửa sổ thứ nhất; kiểm tra cửa sổ thứ hai. | Hai người xem dùng một nguồn video MQTT từ laptop; count không bị nhân đôi. Đóng một người xem không dừng người còn lại. **Hai tab cùng một cửa sổ không đủ chứng minh hai kết nối đồng thời** vì tab bị ẩn tự ngắt video. |
| 17 | Mở tổng cộng 5 cửa sổ đang hiển thị cùng xe, rồi cửa sổ thứ sáu. Quan sát request `stream.mjpg` của cửa sổ thứ sáu trong Network của trình duyệt. Sau đó đóng các cửa sổ thêm. | Năm kết nối được nhận; kết nối thứ sáu trả **HTTP 429**, không tạo nguồn video thứ hai. Không yêu cầu giao diện hiện nguyên mã 429. Đóng toàn bộ người xem: sau khoảng 5 giây `streaming=false`, count tiếp tục. Mở lại một Dashboard để đi tiếp. |

Để quan sát `streaming` và số nguồn phát, dùng MQTT client giám sát đã được cấp quyền Backend với **client ID riêng**, subscribe `smartbus/bus01/vision/status`, `vision/count`, `vision/frame`; chỉ xem trạng thái/kích thước và nhịp bản tin, không lưu payload ảnh. Không dùng tài khoản ESP32 hoặc client ID `backend-smartbus`. Khi tăng người xem từ 1 lên 2, tần suất frame tại broker không tăng gấp đôi. Không coi việc hai cửa sổ cùng có hình là bằng chứng duy nhất của một nguồn phát.

### 4.5. Chặng 4 — mất kết nối và phục hồi trong cùng trạng thái xe

A vẫn ở trong xe, IR/camera=1, Key ON. Không để người qua cửa khi camera dừng vì hệ thống không thể suy ra lượt bị bỏ lỡ.

| Bước | Thao tác | Kết quả mong đợi và điều kiện tiếp tục |
|---|---|---|
| 18 | Khi video đang chạy, **kết thúc cưỡng bức đúng tiến trình Uvicorn của Web** bằng Task Manager. Giữ MongoDB, broker, ESP32 và vision chạy; ghi mốc mất Web. | Dashboard mất kết nối. Không còn gia hạn, laptop tự ngừng video trong tối đa khoảng 30 giây từ lần STREAM_START cuối; giám sát MQTT thấy `streaming=false`. ESP32 vẫn nhận vision/count, sĩ số vẫn 1 và RUNNING. Ctrl+C là đóng có dọn dẹp, không thay thế phép thử chết đột ngột này. |
| 19 | Khởi động lại Web bằng lệnh mục 1, không khởi động lại vision. Đợi WebSocket tự nối lại; đăng nhập lại nếu phiên hết hạn. | Hai node online trở lại, IR/camera vẫn 1, video tự phát khi có người xem. Cảnh báo cũ vẫn CLOSED và dữ liệu lịch sử còn trong MongoDB. Không cần nhập URL camera riêng. |
| 20 | Trong phần Điều khiển, bấm **Tạm dừng camera** (PAUSE), đợi hơn 10 giây; sau đó bấm **Tiếp tục camera** (RESUME). Giữ nguyên vị trí A. | ACKED_OK. PAUSE dừng count và video, status vẫn có nhịp; Web đánh vision offline/dữ liệu cũ khi count quá hạn, sensor vẫn online và IR=1. RESUME khôi phục count với sĩ số 1, không tính lại A; video trở lại khi nhận STREAM_START/gia hạn kế tiếp, thường trong 15 giây cộng thời gian khởi tạo hình. |
| 21 | Rút webcam trong khi node vẫn chạy; chờ trạng thái camera lỗi và count cũ quá hạn. Cắm lại, đợi node mở lại camera. | Không phát lại khung cũ như tín hiệu mới; video báo mất tín hiệu/offline, sensor vẫn hoạt động. Camera phục hồi giữ sĩ số 1, xoá dấu di chuyển cũ, không cộng thêm A. Thời gian mở lại phụ thuộc driver và backoff; ghi thời gian thực tế, không tự đánh pass nếu camera không phục hồi. |
| 22 | Sau khi camera/count đã phục hồi, thả Key OFF. Đợi WARNING xuất hiện như bước 8, ghi mã cảnh báo mới; **ngắt broker hoặc riêng Wi-Fi của ESP32** khoảng 15 giây. | Với IR=1, còi/LED cảnh báo trên ESP32 vẫn chạy cục bộ. Web không còn dữ liệu mới của các node bị ảnh hưởng; nếu ngắt broker, video cũng mất tín hiệu. Gửi FAN_OFF từ Web khi sensor mất kết nối phải đi tới TIMEOUT, không báo ACKED_OK giả. Không chờ Web để quyết định còi. |
| 23 | Khôi phục kết nối đã ngắt; chờ MQTT nối lại và Web nhận dữ liệu mới. A vẫn ở trong. | Node trở lại online, IR/camera vẫn 1; cảnh báo tiếp tục cùng chu kỳ (WARNING hoặc CRITICAL tùy thời gian đã trôi). Nếu vượt mốc nâng cấp thì còi liên tục/quạt tự bật. Event/alert được gửi lại; Web không nhân đôi cảnh báo cùng ID. Lệnh đã TIMEOUT không được xem là một thao tác thành công; dùng lệnh mới khi cần. |
| 24 | Từ Web, bấm **Reset cảnh báo** (ALARM_RESET). Sau ACK, cho A xuống xe đúng chiều rồi nhấn Safety để kết thúc buổi thử. | ACKED_OK, SAFE, cảnh báo CLOSED với `closed_by=REMOTE_RESET`; còi/quạt tự động tắt. Sau A xuống: IR=0, camera=0, video `Vào: 4`, `Ra: 4`. Nếu đã phải khởi động lại vision ngoài kịch bản, các tổng này không còn áp dụng và phải ghi nhận chạy lại chặng. |

### 4.6. Đối chiếu và kết luận toàn bài

Sau bước 24, kiểm tra lịch sử trên Web: BOARD/ALIGHT đúng trình tự; đồ thị sĩ số 0→3→1→0→1→0; cảnh báo thứ nhất đóng bằng Safety, cảnh báo thứ hai đóng bằng lệnh từ Web. Audit có người xác nhận cảnh báo, lệnh điều khiển và VIDEO_VIEW_START/STOP theo người xem/xe; các lần gia hạn video không làm đầy lịch sử commands/Audit. Không có file ảnh/video được tạo trong các dự án.

| Hạng mục ghi nhận | Thực tế / bằng chứng | Kết luận |
|---|---|---|
| Ngày giờ, người chạy, mã xe, phiên bản mã, cấu hình thời gian | Điền khi chạy | Chưa chạy |
| Các mốc sĩ số thực / IR / camera tại bước 4, 5, 12, 14, 24 | Ghi từng lượt; không chỉ số cuối | Chưa chạy |
| T0, thời điểm WARNING, CRITICAL; còi/LED/quạt thật | Ghi thời gian đo và alert_id | Chưa chạy |
| ACK xác nhận / tắt còi / Safety / ALARM_RESET | Ghi actor, cmd_id, closed_by | Chưa chạy |
| Một nguồn video, 5 người xem và HTTP 429 | Ghi số kết nối và nhịp frame tại broker | Chưa chạy |
| Dừng sau người xem cuối / lease khi Web chết | Ghi mốc cuối frame, streaming=false | Chưa chạy |
| Mất/phục hồi camera và MQTT; count khi video hoạt động | Ghi thời gian, sĩ số, lỗi nếu có | Chưa chạy |
| Kết quả toàn bài | Đạt / Không đạt / Chưa đủ điều kiện; liệt kê bước lỗi hoặc bỏ qua | Chưa chạy |

Chỉ đánh **Đạt** khi các bước bắt buộc đã được quan sát thực tế; không lấy kết quả unit test thay cho phần cứng. Nếu thiếu ESP32/webcam, có thể chạy Web + simulator để chuẩn bị kết nối nhưng phải ghi **chưa kiểm thử tích hợp phần cứng**, không kết luận bộ đếm qua cửa hoặc relay đã đạt. Bộ ghép tâm có thể sai khi che khuất/chen lấn; các lượt đi đối hướng đồng thời nên chạy thêm sau bài cơ bản và ghi sai số, không gộp vào sĩ số chuẩn của bài này.

Lệnh kiểm tra hồi quy trước buổi nghiệm thu (không thay thế kịch bản tổng hợp trên):

```powershell
# Từ thư mục gốc, sau khi cài môi trường theo mục 1 và 3:
Push-Location smartbus-web
.\.venv\Scripts\python -m pytest -q
Pop-Location
Push-Location smartbus-vision-node
.\.venv\Scripts\python -m pytest -q
Pop-Location
Push-Location smartbus-sensor-node
pio test -e native
Pop-Location
```

Nếu đang dùng các môi trường kiểm thử sẵn tại thư mục gốc, thay đường dẫn Python bằng `..\.web-check-venv\Scripts\python.exe` hoặc `..\.vision-check-venv\Scripts\python.exe` khi đứng trong dự án tương ứng. Không cần tạo môi trường thứ hai chỉ để chạy lại node.

Hướng dẫn cấu hình chi tiết: [Web](smartbus-web/README.md), [Sensor](smartbus-sensor-node/README.md), [Vision](smartbus-vision-node/README.md).
