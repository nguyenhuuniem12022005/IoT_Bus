# Tài khoản Web và hướng dẫn nạp ESP32-S3

## Đăng nhập SmartBus
- Tên đăng nhập: `admin`
- Mật khẩu: `admin123`
- Trang Web local: http://localhost:8000
- Đây là tài khoản Web, không phải tài khoản MQTT.
- Cấu hình khởi tạo tài khoản nằm trong `.env`: SEED_ADMIN_USERNAME và SEED_ADMIN_PASSWORD.
- Đổi cấu hình seed không tự đổi mật khẩu tài khoản đã có trong MongoDB.

## Nạp firmware bằng VS Code
1. Cài extension PlatformIO IDE trong VS Code.
2. Open Folder: `D:\k7\IoT\prj\smartbus-sensor-node` (thư mục có platformio.ini).
3. Mở `include/secrets.h` đã được tạo. Điền WIFI_SSID, WIFI_PASS và MQTT_PASS của tài khoản esp32-bus01. Giữ chứng chỉ CA đã nhúng, MQTT_PORT=8883, MQTT_TLS=1 và MQTT_TLS_INSECURE=0. Kiểm tra MQTT_HOST bằng địa chỉ sao chép trực tiếp từ EMQX. Wi-Fi cần hỗ trợ 2,4 GHz.
4. Cắm ESP32-S3 bằng cáp USB dữ liệu. Chọn đúng cổng COM trong Device Manager.
5. PlatformIO > PROJECT TASKS > esp32s3 > General > Build. Chờ SUCCESS.
6. Đóng Serial Monitor nếu đang mở, chọn Upload. Chờ SUCCESS.
7. Chọn Monitor, tốc độ 115200, nhấn RESET trên board.
8. Kiểm tra log `Wi-Fi connected` và `MQTT connected`.

Nếu không vào được chế độ nạp: giữ BOOT, nhấn rồi thả RESET, thả BOOT, chọn lại cổng COM rồi Upload. Nạp xong nhấn RESET.

## Lệnh thay cho thao tác giao diện
Chạy trong terminal PlatformIO tại smartbus-sensor-node:

```powershell
pio run -e esp32s3
pio run -e esp32s3 -t upload
pio device monitor -b 115200
```

Nếu có nhiều cổng, thêm `--upload-port COM5` vào lệnh upload và `--port COM5` vào lệnh monitor; thay COM5 bằng cổng thực tế.

## Kiểm tra toàn hệ thống
- Web và camera chạy trên máy tính, không nạp lên ESP32.
- Web cần MongoDB sẵn sàng; /api/health cần mongo=true và mqtt=true.
- Camera chạy bằng `python -m vision_node.main` trong môi trường Python của smartbus-vision-node.
- Trên Dashboard, kiểm tra sensor và vision online sau khi từng thiết bị gửi dữ liệu.
- Hướng dẫn nạp chi tiết: ../../smartbus-sensor-node/docs/HUONG_DAN_NAP_CODE_VSCODE.md.

## Áp dụng mật khẩu khi MongoDB đã chạy
Trong terminal ở thư mục smartbus-web, dùng môi trường Python đã cài requirements:

```powershell
python scripts/reset_admin.py
```

Script cập nhật tài khoản admin theo .env, kể cả tài khoản đã tồn tại, rồi kiểm tra mật khẩu đã lưu. Chỉ đăng nhập khi script báo thành công. Khi soạn hướng dẫn, MongoDB local ở cổng 27017 chưa kết nối được nên chưa xác nhận cập nhật tài khoản trong database.
