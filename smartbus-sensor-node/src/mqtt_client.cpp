#include "mqtt_client.h"
#include "net_manager.h"
#include "secrets.h"
#include <Arduino.h>
#include <ArduinoJson.h>
#include <MQTT.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <atomic>
#include <cstddef>
#include <cstring>
namespace {
using namespace Config;
// Vùng nhớ cố định riêng cho mỗi task, tái sử dụng sau mỗi payload.
class JsonArena : public ArduinoJson::Allocator {
  alignas(std::max_align_t) unsigned char bytes_[JSON_ARENA_SIZE]{};
  size_t used_ = 0;

public:
  void reset() { used_ = 0; }
  void *allocate(size_t size) override {
    constexpr size_t alignment = alignof(std::max_align_t);
    size_t start = (used_ + sizeof(size_t) + alignment - 1) & ~(alignment - 1);
    if (start + size > sizeof(bytes_))
      return nullptr;
    memcpy(bytes_ + start - sizeof(size_t), &size, sizeof(size));
    used_ = start + size;
    return bytes_ + start;
  }
  void deallocate(void *) override {}
  void *reallocate(void *old, size_t size) override {
    if (!old)
      return allocate(size);
    size_t previous = 0;
    memcpy(&previous, static_cast<unsigned char *>(old) - sizeof(size_t),
           sizeof(previous));
    if (size <= previous)
      return old;
    void *next = allocate(size);
    if (next)
      memcpy(next, old, previous);
    return next;
  }
};
JsonArena localArena, networkArena;
struct Message {
  char topic[TOPIC_SIZE]{};
  char payload[MQTT_BUFFER]{};
  bool retained = false;
  int qos = 1;
};
struct Incoming {
  char payload[MQTT_BUFFER]{};
  bool vision = false;
  uint32_t at = 0;
};
QueueHandle_t events, telemetry, inbox, acks;
std::atomic<bool> connected{false};
WiFiClient plain;
WiFiClientSecure secure;
MQTTClient client(MQTT_BUFFER);
char commandTopic[TOPIC_SIZE], visionTopic[TOPIC_SIZE];
Message deferredAck;
bool hasDeferredAck = false;
char pendingId[ID_SIZE]{};
bool pendingOk = false;
char pendingDetail[128]{};
char history[COMMAND_HISTORY][ID_SIZE]{};
size_t historyNext = 0;
bool visionSeen = false;
uint32_t visionAt = 0;
int visionCount = 0;
uint32_t telemetryAt = 0;
void base(JsonDocument &doc, uint64_t ts) {
  doc["ts"] = ts;
  doc["bus_id"] = BUS_ID;
}
Message message(const char *suffix, JsonDocument &doc, int qos = 1,
                bool retained = false) {
  Message m;
  snprintf(m.topic, sizeof(m.topic), "smartbus/%s/%s", BUS_ID, suffix);
  m.qos = qos;
  m.retained = retained;
  if (doc.overflowed() || measureJson(doc) >= sizeof(m.payload)) {
    Serial.println("JSON output too large");
    return m;
  }
  serializeJson(doc, m.payload, sizeof(m.payload));
  return m;
}
void enqueue(const Message &m, QueueHandle_t queue) {
  if (!m.payload[0])
    return;
  if (xQueueSend(queue, &m, 0) != pdTRUE)
    Serial.println("MQTT queue full: newest message dropped");
}
void onMessage(MQTTClient *, char topic[], char bytes[], int length) {
  if (length <= 0 || size_t(length) >= MQTT_BUFFER) {
    Serial.println("MQTT payload size rejected");
    return;
  }
  Incoming msg;
  msg.vision = strcmp(topic, visionTopic) == 0;
  if (!msg.vision && strcmp(topic, commandTopic) != 0)
    return;
  memcpy(msg.payload, bytes, length);
  msg.at = millis();
  if (xQueueSend(inbox, &msg, 0) != pdTRUE)
    Serial.println("MQTT inbox full");
}
bool send(const Message &m) {
  return client.publish(m.topic, m.payload, m.retained, m.qos);
}
void networkTask(void *) {
  NetManager network;
  network.begin();
  snprintf(commandTopic, sizeof(commandTopic), "smartbus/%s/cmd/sensor",
           BUS_ID);
  snprintf(visionTopic, sizeof(visionTopic), "smartbus/%s/vision/count",
           BUS_ID);
#if MQTT_TLS
#if MQTT_TLS_INSECURE
  secure.setInsecure();
#else
  secure.setCACert(MQTT_CA_CERT);
#endif
  client.begin(MQTT_HOST, MQTT_PORT, secure);
#else
  client.begin(MQTT_HOST, MQTT_PORT, plain);
#endif
  client.setOptions(KEEPALIVE_S, true, MQTT_TIMEOUT_MS);
  client.onMessageAdvanced(onMessage);
  char statusTopic[TOPIC_SIZE], will[MQTT_BUFFER], identity[ID_SIZE];
  snprintf(statusTopic, sizeof(statusTopic), "smartbus/%s/sensor/status",
           BUS_ID);
  snprintf(identity, sizeof(identity), "esp32-%s", BUS_ID);
  {
    networkArena.reset();
    JsonDocument w(&networkArena);
    w["bus_id"] = BUS_ID;
    w["node"] = "sensor";
    w["online"] = false;
    serializeJson(w, will, sizeof(will));
  }
  client.setWill(statusTopic, will, true, 1);
  uint32_t attempt = 0, backoff = BACKOFF_MIN_MS;
  bool first = true;
  for (;;) {
    uint32_t now = millis();
    network.update(now);
    if (WiFi.status() != WL_CONNECTED) {
      connected = false;
      if (client.connected())
        client.disconnect();
    } else if (!client.connected()) {
      connected = false;
      if (first || uint32_t(now - attempt) >= backoff) {
        first = false;
        attempt = now;
        // Chứng chỉ TLS cần đồng hồ hợp lệ; việc chờ không ảnh hưởng logic cục
        // bộ.
        bool clockReady =
            !MQTT_TLS || MQTT_TLS_INSECURE || NetManager::epochMs() != 0;
        if (clockReady &&
            client.connect(identity, MQTT_USER, MQTT_PASS)) {
          bool subscribed = client.subscribe(commandTopic, 1) &&
                            client.subscribe(visionTopic, 0);
          networkArena.reset();
          JsonDocument d(&networkArena);
          base(d, NetManager::epochMs());
          d["node"] = "sensor";
          d["online"] = true;
          d["fw"] = FW_VERSION;
          d["ip"] = WiFi.localIP().toString();
          d["rssi"] = WiFi.RSSI();
          if (subscribed && send(message("sensor/status", d, 1, true))) {
            connected = true;
            backoff = BACKOFF_MIN_MS;
            Serial.println("MQTT connected");
          } else
            client.disconnect();
        } else {
          Serial.printf("MQTT connect failed rc=%d\n",
                        int(client.returnCode()));
          backoff = backoff * 2 > BACKOFF_MAX_MS ? BACKOFF_MAX_MS : backoff * 2;
        }
      }
    } else {
      client.loop();
      connected = client.connected();
      if (connected) {
        Message m;
        // Chỉ lấy khỏi hàng đợi sau PUBACK; lỗi kết nối giữ bản tin ở đầu hàng.
        if (xQueuePeek(events, &m, 0) == pdTRUE) {
          if (send(m))
            xQueueReceive(events, &m, 0);
        } else if (xQueuePeek(acks, &m, 0) == pdTRUE) {
          if (send(m))
            xQueueReceive(acks, &m, 0);
        } else if (xQueueReceive(telemetry, &m, 0) == pdTRUE)
          send(m);
        connected = client.connected();
      }
    }
    vTaskDelay(pdMS_TO_TICKS(LOOP_MS));
  }
}
} // namespace
void SensorMqtt::begin() {
  events = xQueueCreate(Config::OFFLINE_CAPACITY, sizeof(Message));
  telemetry = xQueueCreate(1, sizeof(Message));
  inbox = xQueueCreate(Config::INBOX_CAPACITY, sizeof(Incoming));
  acks = xQueueCreate(Config::COMMAND_HISTORY, sizeof(Message));
  configASSERT(events && telemetry && inbox && acks);
  BaseType_t result =
      xTaskCreatePinnedToCore(networkTask, "smartbus-net",
                              Config::NETWORK_STACK, nullptr, 1, nullptr, 0);
  configASSERT(result == pdPASS);
}
bool SensorMqtt::online() const { return connected.load(); }
void SensorMqtt::receive(Inputs &in) {
  in.network_online = online();
  if (!in.network_online)
    visionSeen = false;
  Incoming msg;
  // Một lệnh mỗi vòng; callback mạng chỉ sao chép, không gọi MQTT lồng nhau.
  if (xQueueReceive(inbox, &msg, 0) == pdTRUE) {
    localArena.reset();
    JsonDocument d(&localArena);
    auto error = deserializeJson(d, msg.payload);
    if (error || !d.is<JsonObject>()) {
      Serial.println("Invalid MQTT JSON");
    } else if (msg.vision) {
      bool valid =
          d["bus_id"].is<const char *>() && strcmp(d["bus_id"], BUS_ID) == 0 &&
          d["node"].is<const char *>() && strcmp(d["node"], "vision") == 0 &&
          d["person_count"].is<int>() && d["person_count"].as<int>() >= 0 &&
          d["raw_count"].is<int>() && d["raw_count"].as<int>() >= 0 &&
          d["ts"].is<uint64_t>() && d["frame_id"].is<uint64_t>() &&
          d["fps"].is<float>() && d["model"].is<const char *>() &&
          !d["confidence_avg"].isUnbound() &&
          (d["confidence_avg"].isNull() || d["confidence_avg"].is<float>());
      if (valid && in.network_online) {
        visionSeen = true;
        visionAt = msg.at;
        visionCount = d["person_count"];
      } else
        Serial.println("Invalid or offline vision payload");
    } else {
      const char *id = d["cmd_id"] | "";
      bool duplicate = false;
      for (auto &old : history)
        if (*id && strcmp(old, id) == 0)
          duplicate = true;
      if (!duplicate) {
        bool idValid = *id && strlen(id) < Config::ID_SIZE;
        snprintf(pendingId, sizeof(pendingId), "%s", idValid ? id : "");
        pendingOk = false;
        snprintf(pendingDetail, sizeof(pendingDetail),
                 "Invalid command envelope");
        bool envelope = idValid && d["ts"].is<uint64_t>() &&
                        d["issued_by"].is<const char *>() &&
                        d["params"].is<JsonObject>() &&
                        d["action"].is<const char *>();
        if (envelope) {
          const char *action = d["action"];
          Action parsed = Action::NONE;
          const char *names[] = {"FAN_ON",      "FAN_OFF",     "BUZZER_SILENCE",
                                 "ALARM_RESET", "RESET_COUNT", "TEST_BUZZER"};
          for (size_t i = 0; i < 6; ++i)
            if (strcmp(action, names[i]) == 0)
              parsed = static_cast<Action>(i + 1);
          bool params = true;
          uint32_t duration = Config::FAN_DEFAULT_S;
          if (parsed == Action::FAN_ON) {
            for (JsonPair p : d["params"].as<JsonObject>())
              if (strcmp(p.key().c_str(), "duration_s"))
                params = false;
            if (!d["params"]["duration_s"].isUnbound()) {
              params = params && d["params"]["duration_s"].is<uint32_t>() &&
                       d["params"]["duration_s"].as<uint32_t>() > 0;
              duration = d["params"]["duration_s"] | Config::FAN_DEFAULT_S;
            }
          } else
            params = d["params"].size() == 0;
          pendingOk = parsed != Action::NONE && params;
          if (pendingOk) {
            in.action = parsed;
            in.duration_s =
                duration > Config::FAN_MAX_S ? Config::FAN_MAX_S : duration;
            snprintf(pendingDetail, sizeof(pendingDetail), "%s accepted%s",
                     action, parsed == Action::FAN_ON ? ", timed" : "");
          } else
            snprintf(pendingDetail, sizeof(pendingDetail),
                     "Unsupported action or invalid params");
        }
        if (idValid) {
          snprintf(history[historyNext], Config::ID_SIZE, "%s", id);
          historyNext = (historyNext + 1) % Config::COMMAND_HISTORY;
        }
        // Lệnh thiếu mã vẫn trả ack âm với mã rỗng để báo lỗi định dạng.
        if (!idValid)
          snprintf(pendingId, sizeof(pendingId), "%s", "");
        d.clear();
        localArena.reset();
        d["cmd_id"] = pendingId;
        base(d, in.epoch_ms);
        d["node"] = "sensor";
        d["ok"] = pendingOk;
        d["detail"] = pendingDetail;
        // Chỉ gửi ack sau bước update máy trạng thái qua publish().
        deferredAck = message("cmd/ack", d);
        hasDeferredAck = true;
      }
    }
  }
  in.vision_received = visionSeen;
  in.vision_at_ms = visionAt;
  in.vision_count = visionCount;
}
void SensorMqtt::publish(const Inputs &in, const Outputs &o) {
  for (size_t i = 0; i < o.event_count; ++i) {
    const Event &e = o.events[i];
    localArena.reset();
    JsonDocument d(&localArena);
    base(d, in.epoch_ms);
    d["event"] = e.name;
    d["ir_count"] = e.ir_count;
    auto detail = d["detail"].to<JsonObject>();
    if (strcmp(e.name, "STATE_CHANGED") == 0) {
      detail["from"] = stateName(e.from);
      detail["to"] = stateName(e.to);
    }
    if (strcmp(e.name, "FAN_CHANGED") == 0) {
      detail["on"] = e.on;
      detail["source"] = e.source;
    }
    enqueue(message("sensor/event", d), events);
  }
  if (o.alert.changed) {
    localArena.reset();
    JsonDocument d(&localArena);
    base(d, in.epoch_ms);
    d["alert_id"] = o.alert.id;
    d["level"] = levelName(o.alert.level);
    d["status"] = o.alert.active ? "ACTIVE" : "CLOSED";
    auto reasons = d["reasons"].to<JsonArray>();
    reasons.add("SAFETY_NOT_CONFIRMED");
    if (o.alert.reasons.pir)
      reasons.add("PIR_MOTION_DETECTED");
    if (o.alert.reasons.ir)
      reasons.add("IR_COUNT_POSITIVE");
    if (o.alert.reasons.vision)
      reasons.add("VISION_PERSON_DETECTED");
    if (o.alert.closed_by)
      d["closed_by"] = o.alert.closed_by;
    else
      d["closed_by"] = nullptr;
    enqueue(message("alert", d), events);
  }
  if (hasDeferredAck) {
    enqueue(deferredAck, acks);
    hasDeferredAck = false;
  }
  if (uint32_t(in.now_ms - telemetryAt) < Config::TELEMETRY_MS)
    return;
  telemetryAt = in.now_ms;
  localArena.reset();
  JsonDocument d(&localArena);
  base(d, in.epoch_ms);
  d["ir_count"] = o.ir_count;
  d["ignition"] = in.ignition;
  d["pir_motion"] = in.pir_motion;
  d["safety_confirmed"] = o.safety_confirmed;
  d["state"] = stateName(o.state);
  d["alert_level"] = levelName(o.alert_level);
  d["buzzer"] = o.buzzer_mode != BuzzerMode::OFF;
  d["led"] = ledName(o.led);
  d["fan"] = o.fan_on;
  d["presence"]["pir"] = o.presence.pir;
  d["presence"]["ir"] = o.presence.ir;
  d["presence"]["vision"] = o.presence.vision;
  d["vision_fresh"] = o.vision_fresh;
  d["wifi_rssi"] = WiFi.RSSI();
  d["uptime_s"] = in.now_ms / Config::MS_PER_S;
  d["fw"] = Config::FW_VERSION;
  Message m = message("sensor/telemetry", d, 0);
  xQueueOverwrite(telemetry, &m);
}
