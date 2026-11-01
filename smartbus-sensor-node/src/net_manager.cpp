#include "net_manager.h"
#include "config.h"
#include "secrets.h"
#include <WiFi.h>
#include <sys/time.h>
void NetManager::begin() {
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  backoff_ = Config::BACKOFF_MIN_MS;
  last_ = millis();
  configTime(0, 0, "pool.ntp.org", "time.nist.gov");
}
void NetManager::update(uint32_t now) {
  bool online = WiFi.status() == WL_CONNECTED;
  if (online && !was_online_)
    Serial.printf("Wi-Fi connected IP=%s\n", WiFi.localIP().toString().c_str());
  was_online_ = online;
  if (online) {
    backoff_ = Config::BACKOFF_MIN_MS;
    return;
  }
  if (uint32_t(now - last_) >= backoff_) {
    last_ = now;
    WiFi.reconnect();
    backoff_ = backoff_ * 2 > Config::BACKOFF_MAX_MS ? Config::BACKOFF_MAX_MS
                                                     : backoff_ * 2;
  }
}
uint64_t NetManager::epochMs() {
  timeval tv{};
  gettimeofday(&tv, nullptr);
  return uint64_t(tv.tv_sec) < Config::VALID_EPOCH_S
             ? 0
             : uint64_t(tv.tv_sec) * Config::MS_PER_S +
                   tv.tv_usec / Config::MS_PER_S;
}
