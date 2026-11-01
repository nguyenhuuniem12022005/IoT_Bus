#include "state_machine.h"
#include <climits>
#include <cstdio>
#include <cstring>
using namespace Config;
StateMachine::StateMachine(const char *id) {
  std::snprintf(bus_, sizeof(bus_), "%s", id);
}
void StateMachine::event(const char *name) {
  if (out_.event_count < EVENT_CAPACITY) {
    auto &e = out_.events[out_.event_count++];
    e = Event{};
    e.name = name;
    e.ir_count = out_.ir_count;
  }
}
void StateMachine::transition(State next) {
  if (out_.state == next)
    return;
  State old = out_.state;
  out_.state = next;
  event("STATE_CHANGED");
  out_.events[out_.event_count - 1].from = old;
  out_.events[out_.event_count - 1].to = next;
}
void StateMachine::fan(bool on, bool automatic, uint32_t now,
                       uint32_t duration) {
  if (out_.fan_on != on) {
    event("FAN_CHANGED");
    auto &e = out_.events[out_.event_count - 1];
    e.on = on;
    e.source = automatic ? "AUTO" : "REMOTE";
  }
  out_.fan_on = on;
  fan_auto_ = automatic;
  fan_at_ = now;
  fan_ms_ = (duration > FAN_MAX_S ? FAN_MAX_S : duration) * MS_PER_S;
}
void StateMachine::openAlert(const Inputs &in, AlertLevel level) {
  if (active_level_ == AlertLevel::NONE)
    std::snprintf(
        alert_id_, sizeof(alert_id_), "%s-%llu", bus_,
        static_cast<unsigned long long>(in.epoch_ms ? in.epoch_ms : in.now_ms));
  active_level_ = level;
  alert_reasons_ = out_.presence;
  silenced_ = false;
  out_.alert.changed = true;
  out_.alert.active = true;
  out_.alert.level = level;
  out_.alert.reasons = alert_reasons_;
  std::snprintf(out_.alert.id, sizeof(out_.alert.id), "%s", alert_id_);
}
void StateMachine::closeAlert(const char *reason) {
  if (active_level_ == AlertLevel::NONE)
    return;
  out_.alert.changed = true;
  out_.alert.active = false;
  out_.alert.level = active_level_;
  out_.alert.reasons = alert_reasons_;
  out_.alert.closed_by = reason;
  std::snprintf(out_.alert.id, sizeof(out_.alert.id), "%s", alert_id_);
  active_level_ = AlertLevel::NONE;
  clear_pending_ = false;
  presence_pending_ = false;
  silenced_ = false;
}
const Outputs &StateMachine::update(const Inputs &in) {
  const uint32_t now = in.now_ms;
  out_.event_count = 0;
  out_.alert = AlertChange{};
  if (!initialized_) {
    initialized_ = true;
    ignition_ = in.ignition;
    out_.state = in.ignition ? State::RUNNING : State::SAFE;
  }
  if (in.count_delta > 0) {
    if (out_.ir_count < INT_MAX)
      ++out_.ir_count;
    event("BOARD");
  }
  if (in.count_delta < 0) {
    if (out_.ir_count > 0)
      --out_.ir_count;
    event("ALIGHT");
  }
  if (in.action == Action::RESET_COUNT) {
    out_.ir_count = 0;
    event("COUNT_RESET");
  }
  if (in.pir_motion) {
    pir_seen_ = true;
    pir_at_ = now;
    if (!pir_event_seen_ || uint32_t(now - pir_event_at_) >= PIR_EVENT_MS) {
      event("PIR_MOTION");
      pir_event_seen_ = true;
      pir_event_at_ = now;
    }
  }
  out_.vision_fresh =
      in.network_online && in.vision_received &&
      uint32_t(now - in.vision_at_ms) <= VISION_STALE_S * MS_PER_S;
  out_.presence = {pir_seen_ &&
                       uint32_t(now - pir_at_) <= PIR_RECENT_S * MS_PER_S,
                   out_.ir_count > 0, out_.vision_fresh && in.vision_count > 0};
  if (in.ignition != ignition_) {
    ignition_ = in.ignition;
    out_.safety_confirmed = false;
    test_ = false;
    event(ignition_ ? "IGNITION_ON" : "IGNITION_OFF");
    if (ignition_) {
      closeAlert("IGNITION_ON");
      transition(State::RUNNING);
      fan(false, fan_auto_, now, 0);
    } else {
      off_at_ = now;
      transition(State::CHECKING);
      silenced_ = false;
    }
  }
  if (in.safety_pressed && !ignition_ && out_.state != State::SAFE) {
    out_.safety_confirmed = true;
    event("SAFETY_CONFIRMED");
    closeAlert("SAFETY_BUTTON");
    transition(State::SAFE);
    test_ = false;
    if (fan_auto_)
      fan(false, true, now, 0);
  }
  if (in.action == Action::ALARM_RESET &&
      (out_.state == State::WARNING || out_.state == State::CRITICAL)) {
    closeAlert("REMOTE_RESET");
    transition(State::SAFE);
    test_ = false;
    if (fan_auto_)
      fan(false, true, now, 0);
  }
  const bool has = out_.presence.any();
  if (out_.state == State::CHECKING &&
      uint32_t(now - off_at_) >= CHECK_GRACE_S * MS_PER_S && has) {
    transition(State::WARNING);
    openAlert(in, AlertLevel::WARNING);
    presence_at_ = now;
    presence_pending_ = true;
    clear_pending_ = false;
  }
  if (out_.state == State::WARNING || out_.state == State::CRITICAL) {
    if (has) {
      clear_pending_ = false;
      if (!presence_pending_) {
        presence_pending_ = true;
        presence_at_ = now;
      }
      if (out_.state == State::WARNING &&
          uint32_t(now - presence_at_) >= CRITICAL_AFTER_S * MS_PER_S) {
        transition(State::CRITICAL);
        openAlert(in, AlertLevel::CRITICAL);
        fan(true, true, now, FAN_DEFAULT_S);
      }
    } else {
      presence_pending_ = false;
      if (!clear_pending_) {
        clear_pending_ = true;
        clear_at_ = now;
      }
      if (uint32_t(now - clear_at_) >= CLEAR_AFTER_S * MS_PER_S) {
        closeAlert("NO_PRESENCE");
        transition(State::CHECKING);
        if (fan_auto_)
          fan(false, true, now, 0);
      }
    }
  }
  if (in.action == Action::FAN_ON)
    fan(true, false, now, in.duration_s);
  if (in.action == Action::FAN_OFF)
    fan(false, false, now, 0);
  if (out_.fan_on && uint32_t(now - fan_at_) >= fan_ms_)
    fan(false, fan_auto_, now, 0);
  if (in.action == Action::BUZZER_SILENCE) {
    silenced_ = true;
    test_ = false;
  }
  if (in.action == Action::TEST_BUZZER) {
    test_ = true;
    test_at_ = now;
  }
  if (test_ && uint32_t(now - test_at_) >= TEST_BUZZER_MS)
    test_ = false;
  out_.buzzer_mode = BuzzerMode::OFF;
  // Khi hết bằng chứng, tắt còi ngay; vẫn giữ cảnh báo trong khoảng chống
  // nhiễu.
  if (has && !silenced_) {
    if (out_.state == State::WARNING)
      out_.buzzer_mode = BuzzerMode::INTERMITTENT;
    if (out_.state == State::CRITICAL)
      out_.buzzer_mode = BuzzerMode::CONTINUOUS;
  }
  if (test_)
    out_.buzzer_mode = BuzzerMode::ONE_SHOT_1S;
  out_.alert_level = active_level_;
  out_.led = out_.state == State::RUNNING    ? LedMode::GREEN
             : out_.state == State::SAFE     ? LedMode::OFF
             : out_.state == State::CHECKING ? LedMode::RED
                                             : LedMode::RED_BLINK;
  uint32_t elapsed = uint32_t(now - off_at_);
  out_.grace_remaining_s =
      out_.state == State::CHECKING && elapsed < CHECK_GRACE_S * MS_PER_S
          ? (CHECK_GRACE_S * MS_PER_S - elapsed + MS_PER_S - 1) / MS_PER_S
          : 0;
  return out_;
}
