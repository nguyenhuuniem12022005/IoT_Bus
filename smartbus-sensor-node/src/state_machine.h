#pragma once
#include "types.h"
class StateMachine {
public:
  explicit StateMachine(const char *bus_id = "bus01");
  const Outputs &update(const Inputs &in);

private:
  Outputs out_;
  char bus_[Config::ID_SIZE]{};
  bool initialized_ = false, ignition_ = false, pir_seen_ = false,
       clear_pending_ = false;
  bool presence_pending_ = false, silenced_ = false, fan_auto_ = false,
       test_ = false, pir_event_seen_ = false;
  uint32_t off_at_ = 0, pir_at_ = 0, pir_event_at_ = 0, clear_at_ = 0,
           presence_at_ = 0, fan_at_ = 0, fan_ms_ = 0, test_at_ = 0;
  char alert_id_[Config::ID_SIZE]{};
  Presence alert_reasons_;
  AlertLevel active_level_ = AlertLevel::NONE;
  void event(const char *name);
  void transition(State next);
  void fan(bool on, bool automatic, uint32_t now, uint32_t duration);
  void openAlert(const Inputs &in, AlertLevel level);
  void closeAlert(const char *reason);
};
