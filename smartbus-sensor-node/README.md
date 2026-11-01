# SmartBus — Node cảm biến (Task 2)

## 1. Giới thiệu
ESP32-S3 + IO Shield đọc IR/PIR, quản lý chu kỳ kiểm tra cuối xe và điều khiển còi, LED, quạt, OLED. Task 1 là Web, Task 3 là camera laptop: không import chéo, không cần hai khối đó để chạy. Camera chỉ góp bằng chứng khi MQTT hoạt động và bản tin nhận chưa quá 10 giây. Web không quyết định còi.

## 2. Yêu cầu
Python 3.10–3.12, ESP32-S3 DevKitC-1, IO Shield phù hợp, cáp USB truyền dữ liệu, cảm biến và thiết bị theo bảng dưới. VS Code + PlatformIO IDE là tùy chọn. Native test cần trình biên dịch C++17 trên PATH (Windows: MinGW-w64, Linux: g++, macOS: Xcode Command Line Tools). Chỉ nạp sau khi kiểm tra sơ đồ shield thực tế.

## 3. Cài đặt
Mở terminal tại thư mục `smartbus-sensor-node`:
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
Kiểm tra `pio --version` trả về 6.1.16. Lần đầu cần Internet để tải platform/toolchain/thư viện.

## 4. Đấu nối
| Chức năng | GPIO mặc định | Ghi chú |
|---|---|---|
| IR1 ngoài cửa | 4 | LM393, LOW có vật cản |
| IR2 trong cửa | 6 | LM393, LOW có vật cản |
| PIR HC-SR501 | 5 | HIGH có chuyển động |
| Ignition | 7 | INPUT_PULLUP, LOW đang nổ máy |
| Safety | 11 | INPUT_PULLUP, LOW bấm, chống dội 50 ms |
| Buzzer | 12 | Active buzzer |
| LED xanh | 15 | RGB chung âm, HIGH bật; qua điện trở hạn dòng |
| LED đỏ | 14 | RGB chung âm, HIGH bật; qua điện trở hạn dòng |
| LED blue | 16 | OUTPUT, giữ LOW vì chưa dùng trong trạng thái cảnh báo |
| Relay quạt | 13 | Mức tích cực cấu hình được |
| OLED SDA/SCL | 8/9 | SSD1306 128×64 I2C, 0x3C |

Chỉ đổi GPIO trong `include/pins.h`. Đổi mức IR/relay trong `include/config.h`. GPIO ESP32 dùng mức 3,3 V: không đưa đầu ra 5 V trực tiếp vào GPIO; dùng chuyển mức khi cần. Quạt 5 V lấy nguồn phù hợp qua tiếp điểm relay, không lấy dòng từ GPIO; nối GND chung phía điều khiển, dùng mạch driver và chống điện áp ngược phù hợp. Kiểm tra relay active LOW trước khi gắn tải. Chờ PIR ổn định khi mới cấp nguồn.

## 5. Cấu hình
Windows: `copy include/secrets.example.h include/secrets.h` (PowerShell cũng dùng được).
Linux/macOS: `cp include/secrets.example.h include/secrets.h`.

| Macro | Ý nghĩa |
|---|---|
| WIFI_SSID / WIFI_PASS | Tên/mật khẩu Wi-Fi 2,4 GHz |
| BUS_ID | Xe, mặc định bus01 |
| MQTT_HOST / MQTT_PORT | Broker, 1883 dev hoặc 8883 TLS |
| MQTT_USER | Bắt buộc esp32-{BUS_ID}, đồng thời là client_id |
| MQTT_PASS | Mật khẩu riêng của node |
| MQTT_TLS | 1 bật WiFiClientSecure, 0 dùng dev |
| MQTT_CA_CERT | Chuỗi PEM CA của broker, có thể dùng raw string C++ |
| MQTT_TLS_INSECURE | 0 xác minh CA; 1 bỏ xác minh, **chỉ dùng dev** |

Không commit secrets.h/tools/.env, không gửi mật khẩu vào chat. TLS xác minh CA đợi đồng bộ NTP ở task mạng; cảm biến vẫn hoạt động. Chưa NTP, payload gửi ts=0. Đổi BUS_ID đồng thời trên các node và ACL broker.

## 6. Biên dịch, nạp và xem log
```bash
pio run -e esp32s3
pio run -e esp32s3 -t upload
pio device monitor
```
Hướng dẫn giao diện: [Nạp bằng VS Code](docs/HUONG_DAN_NAP_CODE_VSCODE.md).
Firmware log `SmartBus fw=1.0.0`, `Wi-Fi connected IP=...`, `MQTT connected`. Không log mật khẩu. Chưa có secrets.h thì build báo thiếu file, cần tạo từ mẫu.

## 7. Unit test
```bash
pio test -e native
```
Hai suite kiểm tra IR theo chiều/cửa sổ/nhiễu/chống đếm lặp và máy trạng thái 14 dòng: boot, grace, WARNING/CRITICAL, Safety, ignition, NO_PRESENCE, reset/silence/test còi, quạt kẹp 900 s, reset count, camera cũ/mất mạng, tràn millis. Không cần secrets.h hoặc board cho native.

## 8. Kiểm thử một mình
Sao chép `tools/.env.example` thành `tools/.env`, điền broker và tài khoản thử nghiệm. Chạy ở ba terminal đã kích hoạt venv:
```bash
python tools/mqtt_monitor.py
python tools/fake_backend.py --action FAN_ON --duration 60
python tools/fake_vision.py --count 2 --interval 1
```
Monitor phải thấy telemetry 2 giây/lần, backend nhận ack ok:true, camera phát count 1 giây/lần. Trên broker có ACL chặt, dùng `MQTT_USERNAME=backend` cho monitor/backend, `MQTT_USERNAME=laptop-bus01` cho fake_vision (biến môi trường terminal ghi đè tools/.env). Monitor dùng client_id monitor-bus01, công cụ backend dùng backend; nếu broker buộc username=client_id hãy cấp tài khoản monitor tương ứng. Không chạy fake_backend cùng backend thật có cùng client_id.

Tắt Web và Laptop thật, không chạy fake_vision: bật ignition, đưa vật qua IR1→IR2, tắt ignition, đợi 30 s thấy WARNING rồi 30 s nữa CRITICAL/quạt. Safety đóng cảnh báo, dù IR vẫn dương không kêu lại. Sau chu kỳ ignition mới, RESET_COUNT và chờ PIR hết 30 s: quá grace vẫn CHECKING, còi tắt. Bật fake_vision count 2: WARNING. Tắt fake_vision: sau hơn 10 s camera hết tươi; nếu IR/PIR đều vắng, còi tắt và sau 10 s đóng NO_PRESENCE. Nếu PIR còn phát hiện thì cảnh báo vẫn giữ.

Thử trùng: chạy `python tools/fake_backend.py --action FAN_ON --cmd-id demo-1` hai lần. Lần hai TIMEOUT là đúng vì không ack lại và không gia hạn quạt. Thử lệnh sai `--action UNKNOWN` phải ack ok:false. Bộ nhớ khử trùng giữ 16 mã, mất khi reboot.

Tắt broker/Wi-Fi trong chu kỳ có IR dương: còi/LED vẫn hoạt động. Khôi phục broker: event/alert gửi lại FIFO. Hàng đợi RAM tối đa 20, đầy bỏ bản tin mới và log; reboot mất đệm. QoS 1 có thể giao lặp khi mất PUBACK, backend nên xử lý idempotent. Telemetry chỉ giữ mẫu mới nhất. Kiểm tra trên phần cứng thực mới xác nhận được timing, relay, nguồn và kết nối lại.

## 9. Demo phần cứng 6 bước
1. Ignition ON → RUNNING, LED xanh.
2. Đi qua IR1 rồi IR2 → BOARD, IR=1.
3. Ignition OFF → CHECKING, LED đỏ.
4. Không bấm Safety, giữ IR dương; 30 s đầu còi tắt.
5. Hết 30 s → WARNING còi ngắt quãng; thêm 30 s có người liên tục → CRITICAL còi liên tục, quạt 300 s.
6. Bấm Safety → SAFE, còi/quạt tự động tắt, alert đóng SAFETY_BUTTON.

## 10. Tham số
Tất cả thời gian/ngưỡng nằm trong `include/config.h`.
| Tham số | Mặc định | Ý nghĩa |
|---|---|---|
| CHECK_GRACE_S | 30 | Thời gian kiểm tra cuối xe |
| CRITICAL_AFTER_S | 30 | Có người liên tục từ WARNING |
| PIR_RECENT_S | 30 | Cửa sổ bằng chứng PIR |
| VISION_STALE_S | 10 | Tuổi tối đa từ lúc nhận camera |
| CLEAR_AFTER_S | 10 | Không còn nguồn thấy người trước khi đóng |
| IR_PAIR_WINDOW_MS | 1500 | Cặp IR hợp lệ |
| FAN_DEFAULT_S / FAN_MAX_S | 300 / 900 | Thời lượng quạt |
| IR_ACTIVE_LEVEL / RELAY_ACTIVE_LEVEL | 0 / 0 | LOW tích cực |
| DEBOUNCE_MS / IR_DEBOUNCE_MS | 50 / 20 | Chống dội nút và IR |
| PIR_EVENT_MS | 5000 | Giới hạn event PIR |
| BUZZER_HALF_MS / LED_HALF_MS | 500 / 250 | Còi 1 Hz, LED 2 Hz |
| TEST_BUZZER_MS | 1000 | Test còi |
| DISPLAY_MS / TELEMETRY_MS | 500 / 2000 | Làm tươi màn hình/telemetry |
| BACKOFF_MIN_MS / BACKOFF_MAX_MS | 1000 / 30000 | Kết nối lại |
| KEEPALIVE_S / MQTT_TIMEOUT_MS | 15 / 1000 | MQTT |
| OFFLINE_CAPACITY / COMMAND_HISTORY | 20 / 16 | Đệm/khử trùng |
| MQTT_BUFFER | 1024 | Bộ đệm MQTT |
| WDT_S / LOOP_MS | 5 / 5 | Watchdog và nhường CPU |
| FW_VERSION | 1.0.0 | Phiên bản hợp đồng |

## 11. Cấu trúc thư mục
```
smartbus-sensor-node/
├── README.md
├── requirements.txt                # chứa PlatformIO + thư viện cho tools/
├── .gitignore                      # chặn include/secrets.h, .pio/, .venv/, tools/.env
├── platformio.ini                  # env esp32s3 + env native (chạy unit test)
├── docs/
│   └── HUONG_DAN_NAP_CODE_VSCODE.md   # hướng dẫn nạp code từng bước trong VS Code (mục 3.9)
├── include/
│   ├── pins.h                      # SƠ ĐỒ CHÂN duy nhất
│   ├── config.h                    # tham số mục 3.4 + hằng số thời gian, mức tích cực IR/Relay
│   ├── secrets.example.h           # mẫu: WIFI_SSID, WIFI_PASS, MQTT_HOST, MQTT_PORT, MQTT_USER, MQTT_PASS, MQTT_CA_CERT, BUS_ID
│   └── types.h                     # enum State, AlertLevel, LedMode, BuzzerMode, struct Inputs/Outputs/Event
├── src/
│   ├── main.cpp
│   ├── passenger_counter.h         # THUẦN logic
│   ├── passenger_counter.cpp
│   ├── state_machine.h             # THUẦN logic
│   ├── state_machine.cpp
│   ├── sensors.h                   # đọc IR/PIR/Ignition/Safety + chống dội
│   ├── sensors.cpp
│   ├── actuators.h                 # buzzer, LED, relay quạt (non-blocking)
│   ├── actuators.cpp
│   ├── display.h                   # OLED
│   ├── display.cpp
│   ├── net_manager.h               # Wi-Fi + NTP
│   ├── net_manager.cpp
│   ├── mqtt_client.h               # MQTT(S), publish/subscribe theo hợp đồng, đệm offline, xử lý lệnh
│   └── mqtt_client.cpp
├── test/
│   ├── test_passenger_counter/
│   │   └── test_main.cpp
│   └── test_state_machine/
│       └── test_main.cpp
└── tools/
    ├── .env.example
    ├── mqtt_monitor.py
    ├── fake_vision.py
    └── fake_backend.py
```

## 12. Tích hợp Task 1 & 3
Không có thứ tự khởi động bắt buộc. Node dùng username/client_id esp32-{BUS_ID}; chỉ subscribe `smartbus/{BUS_ID}/cmd/sensor` QoS 1 và `smartbus/{BUS_ID}/vision/count` QoS 0. Publish telemetry QoS 0 không retain mỗi 2 s; event, alert, ack QoS 1 không retain; status QoS 1 retain, có LWT online:false. Hai luồng sensor và vision độc lập, cả hai gửi thẳng broker.

Thay PubSubClient bằng `256dpi/MQTT@2.5.2` vì PubSubClient chỉ publish QoS 0. Bộ đệm 1024 được truyền qua constructor MQTTClient, tương đương mục tiêu setBufferSize(1024). API publish có QoS và retained: https://github.com/256dpi/arduino-mqtt. Wi-Fi/TLS/MQTT và OLED chạy các task riêng; các queue FreeRTOS chuyển dữ liệu sang vòng logic, không gọi publish từ callback. ArduinoJson 7 dùng allocator RAM cố định riêng cho mỗi task, không cấp phát heap khi tạo/parse payload; không nối String payload lớn, payload truyền qua char[] cố định.

Giả định: TEST_BUZZER là lệnh kiểm tra chủ động, được kêu 1 s ngoài điều kiện báo động. Khi không còn bằng chứng, tắt còi ngay nhưng đợi CLEAR_AFTER_S mới đóng alert. CLOSED giữ reasons lần tạo/nâng gần nhất để luôn có nguồn thấy người. ALARM_RESET kết thúc chu kỳ đến lần tắt máy kế tiếp và tắt quạt AUTO; không đánh dấu đã bấm Safety. Quạt REMOTE giữ khi Safety/NO_PRESENCE/reset, nhưng ignition ON tắt mọi quạt. FAN_ON duration phải là số nguyên dương, mặc định 300, kẹp 900. Hai IR kích hoạt cùng lúc bị bỏ qua vì không biết chiều. Boot OFF giữ SAFE, không tự mở chu kỳ kiểm tra.

## 13. Xử lý sự cố
| Triệu chứng | Cách xử lý |
|---|---|
| Không Wi-Fi | Kiểm tra SSID, mật khẩu, mạng 2,4 GHz, nguồn |
| MQTT rc khác 0 | Kiểm tra host/port/tài khoản esp32-{BUS_ID}, ACL và client_id trùng |
| TLS lỗi | Kiểm tra CA, hostname, NTP, port 8883; không bỏ xác minh trên triển khai |
| IR ngược chiều | Đổi vị trí IR1/IR2 hoặc ánh xạ trong pins.h |
| OLED tối | Kiểm tra SDA/SCL, địa chỉ 0x3C và nguồn; vắng OLED không dừng logic |
| Không có ack lần hai | cmd_id trùng bị bỏ qua theo hợp đồng |
| Native không có g++ | Cài MinGW-w64/build-essential/Xcode tools, mở terminal mới |

Kết quả kiểm tra trên máy phát triển: cài các phiên bản trong requirements vào venv mới; build ESP32-S3 thành công với cấu hình mẫu, cả nhánh dev và nhánh TLS (bản cuối đã tách tác vụ OLED); `pio test -e native` đạt 16/16 test. Kiểm tra thêm cú pháp ba script Python, CLI giả lập, timeout khi broker vắng, cấp phát JSON cố định và tái sử dụng bộ nhớ cho ack. Đối chiếu mã tạo payload với danh sách trường hợp đồng; kiểm tra đúng hai subscribe, QoS/retain của telemetry/status/LWT. Chưa nghiệm thu publish/ack/khử trùng qua broker với firmware thật, reconnect/offline FIFO trên board, TLS handshake, nạp code, cảm biến, còi, relay hoặc OLED.

Đây là mô hình học tập; cần nghiệm thu phần cứng và kiểm chứng thực tế trước khi dùng trên xe.
