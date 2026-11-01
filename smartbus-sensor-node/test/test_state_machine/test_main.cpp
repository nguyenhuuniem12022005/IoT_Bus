#include "../../src/state_machine.h"
#include <cstring>
#include <unity.h>
void setUp() {}
void tearDown() {}
static void tick(StateMachine &m, Inputs &i, uint32_t now) {
  i.now_ms = now;
  m.update(i);
  i.count_delta = 0;
  i.safety_pressed = false;
  i.action = Action::NONE;
}
static void checking(StateMachine &m, Inputs &i) {
  i.ignition = true;
  tick(m, i, 0);
  i.ignition = false;
  tick(m, i, 100);
}
void boot_and_nonnegative() {
  StateMachine m;
  Inputs i;
  TEST_ASSERT_EQUAL(int(State::SAFE), int(m.update(i).state));
  i.count_delta = -1;
  TEST_ASSERT_EQUAL(0, m.update(i).ir_count);
  i.ignition = true;
  TEST_ASSERT_EQUAL(int(State::RUNNING), int(m.update(i).state));
}
void two_conditions() {
  StateMachine m;
  Inputs i;
  checking(m, i);
  i.count_delta = 1;
  TEST_ASSERT_EQUAL(int(BuzzerMode::OFF), int(m.update(i).buzzer_mode));
  i.count_delta = 0;
  i.action = Action::RESET_COUNT;
  tick(m, i, 200);
  i.now_ms = 30100;
  const auto &o = m.update(i);
  TEST_ASSERT_EQUAL(int(State::CHECKING), int(o.state));
  TEST_ASSERT_EQUAL(int(BuzzerMode::OFF), int(o.buzzer_mode));
  TEST_ASSERT_EQUAL(int(LedMode::RED), int(o.led));
}
void warning_critical_safety() {
  StateMachine m;
  Inputs i;
  checking(m, i);
  i.count_delta = 1;
  tick(m, i, 200);
  i.now_ms = 30100;
  auto w = m.update(i);
  TEST_ASSERT_EQUAL(int(State::WARNING), int(w.state));
  TEST_ASSERT_EQUAL_STRING("bus01-30100", w.alert.id);
  TEST_ASSERT_TRUE(w.alert.reasons.ir);
  i.now_ms = 60100;
  auto c = m.update(i);
  TEST_ASSERT_EQUAL(int(State::CRITICAL), int(c.state));
  TEST_ASSERT_EQUAL_STRING(w.alert.id, c.alert.id);
  TEST_ASSERT_TRUE(c.fan_on);
  i.safety_pressed = true;
  i.now_ms = 60101;
  auto s = m.update(i);
  TEST_ASSERT_EQUAL(int(State::SAFE), int(s.state));
  TEST_ASSERT_TRUE(s.safety_confirmed);
  TEST_ASSERT_FALSE(s.fan_on);
  TEST_ASSERT_EQUAL_STRING("SAFETY_BUTTON", s.alert.closed_by);
  i.safety_pressed = false;
  i.now_ms = 999999;
  TEST_ASSERT_EQUAL(int(BuzzerMode::OFF), int(m.update(i).buzzer_mode));
}
void camera_only_stale_clear() {
  StateMachine m;
  Inputs i;
  checking(m, i);
  i.network_online = true;
  i.vision_received = true;
  i.vision_count = 2;
  i.vision_at_ms = 30100;
  i.now_ms = 30100;
  auto o = m.update(i);
  TEST_ASSERT_TRUE(o.presence.vision);
  TEST_ASSERT_EQUAL(int(State::WARNING), int(o.state));
  i.now_ms = 40100;
  TEST_ASSERT_TRUE(m.update(i).vision_fresh);
  i.now_ms = 40101;
  TEST_ASSERT_EQUAL(int(BuzzerMode::OFF), int(m.update(i).buzzer_mode));
  i.now_ms = 50100;
  TEST_ASSERT_EQUAL(int(State::WARNING), int(m.update(i).state));
  i.now_ms = 50101;
  o = m.update(i);
  TEST_ASSERT_EQUAL(int(State::CHECKING), int(o.state));
  TEST_ASSERT_EQUAL_STRING("NO_PRESENCE", o.alert.closed_by);
  TEST_ASSERT_TRUE(o.alert.reasons.vision);
}
void safety_during_grace() {
  StateMachine m;
  Inputs i;
  checking(m, i);
  i.safety_pressed = true;
  i.count_delta = 1;
  tick(m, i, 101);
  i.now_ms = 100000;
  auto o = m.update(i);
  TEST_ASSERT_EQUAL(int(State::SAFE), int(o.state));
  TEST_ASSERT_EQUAL(int(BuzzerMode::OFF), int(o.buzzer_mode));
}
void ignition_closes_and_stops_remote_fan() {
  StateMachine m;
  Inputs i;
  checking(m, i);
  i.count_delta = 1;
  tick(m, i, 200);
  tick(m, i, 30100);
  i.action = Action::FAN_ON;
  tick(m, i, 30200);
  i.ignition = true;
  i.now_ms = 30300;
  auto o = m.update(i);
  TEST_ASSERT_EQUAL_STRING("IGNITION_ON", o.alert.closed_by);
  TEST_ASSERT_EQUAL(int(State::RUNNING), int(o.state));
  TEST_ASSERT_FALSE(o.fan_on);
  TEST_ASSERT_FALSE(o.safety_confirmed);
}
void silence_reset_test() {
  StateMachine m;
  Inputs i;
  checking(m, i);
  i.count_delta = 1;
  tick(m, i, 200);
  tick(m, i, 30100);
  i.action = Action::BUZZER_SILENCE;
  i.now_ms = 30200;
  TEST_ASSERT_EQUAL(int(BuzzerMode::OFF), int(m.update(i).buzzer_mode));
  i.action = Action::NONE;
  i.now_ms = 60100;
  TEST_ASSERT_EQUAL(int(BuzzerMode::CONTINUOUS), int(m.update(i).buzzer_mode));
  i.action = Action::ALARM_RESET;
  i.now_ms = 60101;
  auto o = m.update(i);
  TEST_ASSERT_EQUAL_STRING("REMOTE_RESET", o.alert.closed_by);
  TEST_ASSERT_EQUAL(int(State::SAFE), int(o.state));
  TEST_ASSERT_FALSE(o.fan_on);
  i.action = Action::TEST_BUZZER;
  i.now_ms = 60200;
  TEST_ASSERT_EQUAL(int(BuzzerMode::ONE_SHOT_1S), int(m.update(i).buzzer_mode));
  i.action = Action::NONE;
  i.now_ms = 61199;
  TEST_ASSERT_EQUAL(int(BuzzerMode::ONE_SHOT_1S), int(m.update(i).buzzer_mode));
  i.now_ms = 61200;
  TEST_ASSERT_EQUAL(int(BuzzerMode::OFF), int(m.update(i).buzzer_mode));
}
void fan_clamp_reset_count() {
  StateMachine m;
  Inputs i;
  i.action = Action::FAN_ON;
  i.duration_s = 1000;
  TEST_ASSERT_TRUE(m.update(i).fan_on);
  i.action = Action::NONE;
  i.now_ms = 899999;
  TEST_ASSERT_TRUE(m.update(i).fan_on);
  i.now_ms = 900000;
  TEST_ASSERT_FALSE(m.update(i).fan_on);
  i.action = Action::FAN_ON;
  i.now_ms = 900001;
  TEST_ASSERT_TRUE(m.update(i).fan_on);
  i.action = Action::FAN_OFF;
  TEST_ASSERT_FALSE(m.update(i).fan_on);
  i.action = Action::NONE;
  i.count_delta = 1;
  TEST_ASSERT_EQUAL(1, m.update(i).ir_count);
  i.count_delta = 0;
  i.action = Action::RESET_COUNT;
  auto o = m.update(i);
  TEST_ASSERT_EQUAL(0, o.ir_count);
  TEST_ASSERT_EQUAL_STRING("COUNT_RESET", o.events[0].name);
}
void presence_must_be_continuous() {
  StateMachine m;
  Inputs i;
  checking(m, i);
  i.count_delta = 1;
  tick(m, i, 200);
  tick(m, i, 30100);
  i.action = Action::RESET_COUNT;
  tick(m, i, 50000);
  i.count_delta = 1;
  tick(m, i, 55000);
  i.now_ms = 60100;
  TEST_ASSERT_EQUAL(int(State::WARNING), int(m.update(i).state));
  i.now_ms = 85000;
  TEST_ASSERT_EQUAL(int(State::CRITICAL), int(m.update(i).state));
}
void pir_expiry_and_throttle() {
  StateMachine m;
  Inputs i;
  checking(m, i);
  i.pir_motion = true;
  tick(m, i, 30100);
  i.now_ms = 30200;
  auto o = m.update(i);
  TEST_ASSERT_EQUAL(0, o.event_count);
  i.now_ms = 35100;
  o = m.update(i);
  TEST_ASSERT_EQUAL_STRING("PIR_MOTION", o.events[0].name);
  i.pir_motion = false;
  i.now_ms = 65101;
  TEST_ASSERT_FALSE(m.update(i).presence.pir);
}
void offline_camera_and_epoch() {
  StateMachine m;
  Inputs i;
  checking(m, i);
  i.vision_received = true;
  i.vision_count = 1;
  i.vision_at_ms = 30100;
  i.now_ms = 30100;
  TEST_ASSERT_EQUAL(int(State::CHECKING), int(m.update(i).state));
  i.network_online = true;
  i.epoch_ms = 1767225630000ULL;
  auto o = m.update(i);
  TEST_ASSERT_EQUAL_STRING("bus01-1767225630000", o.alert.id);
  i.network_online = false;
  TEST_ASSERT_FALSE(m.update(i).vision_fresh);
}
void wrap_and_remote_fan_survives_safety() {
  StateMachine m;
  Inputs i;
  i.ignition = true;
  tick(m, i, UINT32_MAX - 20000);
  i.ignition = false;
  tick(m, i, UINT32_MAX - 10000);
  i.count_delta = 1;
  tick(m, i, UINT32_MAX - 9000);
  i.now_ms = 19999;
  TEST_ASSERT_EQUAL(int(State::WARNING), int(m.update(i).state));
  i.action = Action::FAN_ON;
  tick(m, i, 20000);
  i.safety_pressed = true;
  i.now_ms = 20001;
  TEST_ASSERT_TRUE(m.update(i).fan_on);
}
void critical_clear_and_auto_expiry() {
  StateMachine m;
  Inputs i;
  checking(m, i);
  i.count_delta = 1;
  tick(m, i, 200);
  tick(m, i, 30100);
  tick(m, i, 60100);
  i.action = Action::RESET_COUNT;
  tick(m, i, 60200);
  i.now_ms = 70200;
  auto o = m.update(i);
  TEST_ASSERT_EQUAL(int(State::CHECKING), int(o.state));
  TEST_ASSERT_FALSE(o.fan_on);
  TEST_ASSERT_EQUAL_STRING("NO_PRESENCE", o.alert.closed_by);
  i.count_delta = 1;
  tick(m, i, 70300);
  tick(m, i, 100300);
  i.now_ms = 400299;
  TEST_ASSERT_TRUE(m.update(i).fan_on);
  i.now_ms = 400300;
  o = m.update(i);
  TEST_ASSERT_FALSE(o.fan_on);
  TEST_ASSERT_EQUAL(int(State::CRITICAL), int(o.state));
}
int main() {
  UNITY_BEGIN();
  RUN_TEST(boot_and_nonnegative);
  RUN_TEST(two_conditions);
  RUN_TEST(warning_critical_safety);
  RUN_TEST(camera_only_stale_clear);
  RUN_TEST(safety_during_grace);
  RUN_TEST(ignition_closes_and_stops_remote_fan);
  RUN_TEST(silence_reset_test);
  RUN_TEST(fan_clamp_reset_count);
  RUN_TEST(presence_must_be_continuous);
  RUN_TEST(pir_expiry_and_throttle);
  RUN_TEST(offline_camera_and_epoch);
  RUN_TEST(wrap_and_remote_fan_survives_safety);
  RUN_TEST(critical_clear_and_auto_expiry);
  return UNITY_END();
}
