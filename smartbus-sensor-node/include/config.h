#pragma once
#include <cstddef>
#include <cstdint>
#ifndef SMARTBUS_RELAY_ACTIVE_LEVEL
#define SMARTBUS_RELAY_ACTIVE_LEVEL 0
#endif
namespace Config {
constexpr const char *FW_VERSION = "1.0.0";
constexpr uint32_t CHECK_GRACE_S = 30, CRITICAL_AFTER_S = 30, PIR_RECENT_S = 30;
constexpr uint32_t VISION_STALE_S = 10, CLEAR_AFTER_S = 10,
                   IR_PAIR_WINDOW_MS = 1500;
constexpr uint32_t FAN_DEFAULT_S = 300, FAN_MAX_S = 900, MS_PER_S = 1000;
constexpr uint32_t DEBOUNCE_MS = 50, IR_DEBOUNCE_MS = 20, PIR_EVENT_MS = 5000;
constexpr uint32_t BUZZER_HALF_MS = 500, LED_HALF_MS = 250,
                   TEST_BUZZER_MS = 1000;
constexpr uint32_t DISPLAY_MS = 500, TELEMETRY_MS = 2000, LOOP_MS = 5;
constexpr uint32_t BACKOFF_MIN_MS = 1000, BACKOFF_MAX_MS = 30000,
                   MQTT_TIMEOUT_MS = 1000;
constexpr uint32_t KEEPALIVE_S = 15, WDT_S = 5, SERIAL_BAUD = 115200;
constexpr uint32_t DISPLAY_STACK = 4096;
constexpr uint32_t NETWORK_STACK = 12288, I2C_TIMEOUT_MS = 10;
constexpr uint64_t VALID_EPOCH_S = 1700000000ULL;
constexpr int IR_ACTIVE_LEVEL = 0, RELAY_ACTIVE_LEVEL = SMARTBUS_RELAY_ACTIVE_LEVEL, OLED_ADDRESS = 0x3c;
constexpr size_t MQTT_BUFFER = 1024, OFFLINE_CAPACITY = 20,
                 COMMAND_HISTORY = 16;
constexpr size_t EVENT_CAPACITY = 12, ID_SIZE = 80, TOPIC_SIZE = 128,
                 INBOX_CAPACITY = 8;
constexpr size_t JSON_ARENA_SIZE = 6144;
} // namespace Config
