# Hướng dẫn nạp ESP32-S3 bằng VS Code

## 1. Chuẩn bị
1. Cài Python 3.10–3.12, bật tùy chọn thêm Python vào PATH; cài VS Code. Trong VS Code, bấm biểu tượng Extensions (các ô vuông) ở thanh trái, tìm **PlatformIO IDE** và chọn Install. Khởi động lại khi được yêu cầu. **Kết quả mong đợi:** thấy biểu tượng PlatformIO ở thanh trái.
2. Dùng cáp USB truyền dữ liệu. Trên Windows, mở Device Manager, cắm/rút board để xem thiết bị xuất hiện. Nếu board dùng cầu USB UART CP210x/CH340 nhưng báo Unknown device, lấy driver đúng chip từ nhà sản xuất Silicon Labs/WCH; USB gốc S3 thường không cần driver đó. **Kết quả mong đợi:** có thiết bị USB/COM nhận diện được.

## 2. Mở đúng thư mục
3. Chọn **File → Open Folder**, chọn `smartbus-sensor-node` có `platformio.ini`. Nên đặt đường dẫn ngắn, không dấu, không khoảng trắng. Đợi PlatformIO tải toolchain lần đầu, có thể mất vài phút. **Kết quả mong đợi:** Explorer hiện include/src/test/tools và PlatformIO nhận dự án.

## 3. Tạo cấu hình riêng
4. Trong Explorer, sao chép `include/secrets.example.h`, đổi tên bản sao thành `secrets.h`. Điền Wi-Fi và MQTT theo README. Không commit secrets.h, không dán mật khẩu vào chat AI. **Kết quả mong đợi:** có secrets.h với BUS_ID đúng và username esp32-{BUS_ID}.

## 4. Chọn môi trường
5. Ở thanh trạng thái phía dưới, bấm mục môi trường PlatformIO (có thể ghi Default), chọn **esp32s3**. Không chọn native để nạp board. **Kết quả mong đợi:** tác vụ Build/Upload dùng esp32s3.

## 5. Build, Upload, Serial Monitor, Clean
6. Thanh trạng thái dưới cùng: dấu tích **Build** biên dịch, mũi tên **Upload** nạp, biểu tượng phích cắm **Serial Monitor** xem log, thùng rác **Clean** xóa sản phẩm biên dịch. Nếu phiên bản extension ẩn biểu tượng, bấm PlatformIO bên trái → **PROJECT TASKS → esp32s3 → General → Build/Upload/Monitor/Clean**. Chạy Build trước, cắm board rồi Upload; đóng Monitor trước khi nạp lại. **Kết quả mong đợi:** Build và Upload báo SUCCESS; Monitor tốc độ 115200.

## 6. Tìm cổng
7. Windows: Device Manager → **Ports (COM & LPT)**; macOS: `/dev/cu.usbmodem*` hoặc `/dev/cu.usbserial*`; Linux: `/dev/ttyACM*` hoặc `/dev/ttyUSB*`. Rút/cắm để xác định đúng cổng, có thể dùng `pio device list`. Nếu nhiều board: `pio run -e esp32s3 -t upload --upload-port COM5`, `pio device monitor --port COM5`; hoặc đặt `upload_port = COM5`, `monitor_port = COM5` trong env esp32s3 của platformio.ini. Đổi COM5 thành cổng thật. **Kết quả mong đợi:** công cụ chọn đúng board.

## 7. Board có hai cổng USB
8. Cổng ghi UART dùng cầu USB UART; cấu hình mặc định dùng cổng này cho nạp/log. Cổng USB/OTG nối USB gốc ESP32-S3 cũng có thể nạp, nhưng COM có thể đổi khi vào bootloader. Muốn Serial xuất qua USB gốc, thêm `-DARDUINO_USB_CDC_ON_BOOT=1` vào build_flags của esp32s3, giữ cờ CORE_DEBUG_LEVEL sẵn có, build/nạp lại và chọn cổng mới sau RESET. Không thấy log: kiểm tra cáp, cổng đang cắm, baud 115200, cờ CDC và bấm RESET sau khi mở Monitor. **Kết quả mong đợi:** thấy dòng SmartBus fw trên cổng đã chọn.

## 8. Nạp thủ công
9. Nếu tự động nạp thất bại, giữ **BOOT**, nhấn rồi thả **RESET**, thả **BOOT**, kiểm tra lại cổng và chọn Upload. Nạp xong nhấn RESET. **Kết quả mong đợi:** công cụ kết nối bootloader và Upload SUCCESS, sau RESET chương trình chạy.

## 9. Terminal thay giao diện
10. Chọn **Terminal → New Terminal**, kiểm tra thư mục đang là smartbus-sensor-node. Tạo venv và cài đặt đúng đoạn dưới (chỉ lần đầu):
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
11. Kích hoạt venv bằng dòng tương ứng hệ điều hành ở trên, rồi chạy:
```bash
pio --version
pio run -e esp32s3
pio run -e esp32s3 -t upload
pio device monitor
```
**Kết quả mong đợi:** PlatformIO 6.1.16, build/upload SUCCESS. Thoát monitor bằng Ctrl+C.

## 10. Log và dữ liệu mong đợi
12. Mở Monitor rồi RESET. Khi cấu hình và broker đúng, firmware thực sự in các dòng dạng:
```text
SmartBus fw=1.0.0
Wi-Fi connected IP=192.168.1.50
MQTT connected
```
IP là ví dụ. Nếu mạng không hoạt động, còi/LED vẫn xử lý cục bộ. Sao chép tools/.env.example thành tools/.env, điền tài khoản theo README; mở terminal thứ hai, kích hoạt venv, chạy `python tools/mqtt_monitor.py`. **Kết quả mong đợi:** thấy `smartbus/bus01/sensor/telemetry` mỗi 2 giây và status online:true retained.

## 11. Unit test không cần board
13. Cài trình biên dịch C++17 trên PATH (MinGW-w64 trên Windows, g++ trên Linux, Xcode Command Line Tools trên macOS), trong venv chạy `pio test -e native`. **Kết quả mong đợi:** hai suite báo PASSED; không yêu cầu cắm board hay tạo secrets.h.

## 12. Lỗi thường gặp
14. Tra bảng, sửa đúng nguyên nhân rồi chạy lại bước liên quan. **Kết quả mong đợi:** Build/Upload/Monitor hoạt động.

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không thấy COM | Cáp chỉ sạc hoặc thiếu driver | Đổi cáp dữ liệu, kiểm tra chip USB và driver |
| Wrong boot mode detected / Failed to connect | Chưa vào bootloader | Giữ BOOT, nhấn RESET, thả BOOT, nạp lại |
| Cổng bận/Access denied | Monitor hoặc ứng dụng khác giữ cổng | Đóng Monitor và ứng dụng dùng cổng trước Upload |
| Permission denied Linux | Thiếu quyền serial | Thêm user vào nhóm dialout, đăng xuất/đăng nhập lại |
| Thiếu secrets.h | Chưa tạo cấu hình | Copy secrets.example.h thành secrets.h |
| Tải platform/thư viện chậm hoặc lỗi | DNS/proxy/Internet | Kiểm tra mạng, proxy và chạy Build lại |
| Lỗi đường dẫn dấu/khoảng trắng | Toolchain không xử lý đường dẫn | Chuyển dự án sang đường dẫn ngắn không dấu |
| Nạp xong không chạy | Còn ở bootloader | Nhấn RESET, kiểm tra lại COM |
| Reset khi bật relay/quạt | Sụt nguồn/nhiễu tải | Dùng nguồn quạt phù hợp, driver và chống nhiễu, kiểm tra GND |
| Xung đột extension | Arduino/ESP-IDF cùng quản lý cổng/build | Tắt extension xung đột cho workspace |
| Monitor không có log | Sai UART/USB CDC hoặc baud | Làm bước 7, chọn lại COM, baud 115200 |
| Native thiếu g++ | Chưa cài compiler/PATH | Cài compiler C++17, mở terminal mới |
| Không MQTT connected | Host/port/credential/ACL sai | Đối chiếu cấu hình và broker; không chia sẻ mật khẩu |
| TLS thất bại | CA hoặc NTP chưa đúng | Sửa CA/hostname, cho phép NTP, giữ xác minh chứng chỉ |

## 13. Checklist nạp thành công
15. Đánh dấu sau khi tự kiểm chứng. **Kết quả mong đợi:** đủ cả 5 ô:
- [ ] Biên dịch SUCCESS.
- [ ] Nạp SUCCESS.
- [ ] Thấy log Wi-Fi connected và IP.
- [ ] Thấy log MQTT connected.
- [ ] mqtt_monitor.py nhận sensor/telemetry.
