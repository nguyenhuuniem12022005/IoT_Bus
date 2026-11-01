#pragma once
#include "config.h"
#include <cstddef>
#include <cstdint>
enum class State { RUNNING, CHECKING, WARNING, CRITICAL, SAFE };
enum class AlertLevel { NONE, WARNING, CRITICAL };
enum class LedMode { OFF, GREEN, RED, RED_BLINK };
enum class BuzzerMode { OFF, INTERMITTENT, CONTINUOUS, ONE_SHOT_1S };
enum class Action {
  NONE,
  FAN_ON,
  FAN_OFF,
  BUZZER_SILENCE,
  ALARM_RESET,
  RESET_COUNT,
  TEST_BUZZER
};
struct Presence {
  bool pir = false, ir = false, vision = false;
  bool any() const { return pir || ir || vision; }
};
struct Inputs {
  uint32_t now_ms = 0;
  uint64_t epoch_ms = 0;
  bool ignition = false, safety_pressed = false, pir_motion = false,
       network_online = false;
  int count_delta = 0;
  bool vision_received = false;
  uint32_t vision_at_ms = 0;
  int vision_count = 0;
  Action action = Action::NONE;
  uint32_t duration_s = Config::FAN_DEFAULT_S;
};
struct Event {
  const char *name = "";
  State from = State::SAFE, to = State::SAFE;
  bool on = false;
  const char *source = "AUTO";
  int ir_count = 0;
};
struct AlertChange {
  bool changed = false, active = false;
  AlertLevel level = AlertLevel::NONE;
  char id[Config::ID_SIZE]{};
  Presence reasons;
  const char *closed_by = nullptr;
};
struct Outputs {
  State state = State::SAFE;
  AlertLevel alert_level = AlertLevel::NONE;
  LedMode led = LedMode::OFF;
  BuzzerMode buzzer_mode = BuzzerMode::OFF;
  bool fan_on = false, safety_confirmed = false, vision_fresh = false;
  int ir_count = 0;
  uint32_t grace_remaining_s = 0;
  Presence presence;
  Event events[Config::EVENT_CAPACITY]{};
  size_t event_count = 0;
  AlertChange alert;
};
inline const char *stateName(State s) {
  const char *a[] = {"RUNNING", "CHECKING", "WARNING", "CRITICAL", "SAFE"};
  return a[static_cast<int>(s)];
}
inline const char *levelName(AlertLevel s) {
  const char *a[] = {"NONE", "WARNING", "CRITICAL"};
  return a[static_cast<int>(s)];
}
inline const char *ledName(LedMode s) {
  const char *a[] = {"off", "green", "red", "red_blink"};
  return a[static_cast<int>(s)];
}
