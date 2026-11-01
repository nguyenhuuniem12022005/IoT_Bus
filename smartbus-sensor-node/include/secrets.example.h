#pragma once
#define WIFI_SSID "YOUR_WIFI_SSID"
#define WIFI_PASS "YOUR_WIFI_PASSWORD"
#define BUS_ID "bus01"
#define MQTT_HOST "broker.example.com"
#define MQTT_PORT 1883
#define MQTT_USER "esp32-" BUS_ID
#define MQTT_PASS "YOUR_DEVICE_PASSWORD"
#define MQTT_TLS 0
// Chỉ dùng chế độ không xác minh chứng chỉ trong môi trường thử nghiệm.
#define MQTT_TLS_INSECURE 0
#define MQTT_CA_CERT ""
