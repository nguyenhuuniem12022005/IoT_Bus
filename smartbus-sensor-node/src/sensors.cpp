#include "sensors.h"
#include "pins.h"
#include <Arduino.h>
bool Sensors::Debouncer::update(bool next, uint32_t now, uint32_t interval) {
  if (next != raw) {
    raw = next;
    at = now;
  }
  bool old = value;
  if (uint32_t(now - at) >= interval)
    value = raw;
  return !old && value;
}
void Sensors::begin() {
  pinMode(Pins::IR1, INPUT_PULLUP);
  pinMode(Pins::IR2, INPUT_PULLUP);
  pinMode(Pins::PIR, INPUT);
  pinMode(Pins::IGNITION, INPUT_PULLUP);
  pinMode(Pins::SAFETY, INPUT_PULLUP);
  ignition_.value = ignition_.raw = digitalRead(Pins::IGNITION) == LOW;
  safety_.value = safety_.raw = digitalRead(Pins::SAFETY) == LOW;
}
void Sensors::read(Inputs &in) {
  ir1_.update(digitalRead(Pins::IR1) == Config::IR_ACTIVE_LEVEL, in.now_ms,
              Config::IR_DEBOUNCE_MS);
  ir2_.update(digitalRead(Pins::IR2) == Config::IR_ACTIVE_LEVEL, in.now_ms,
              Config::IR_DEBOUNCE_MS);
  ignition_.update(digitalRead(Pins::IGNITION) == LOW, in.now_ms,
                   Config::DEBOUNCE_MS);
  in.safety_pressed = safety_.update(digitalRead(Pins::SAFETY) == LOW,
                                     in.now_ms, Config::DEBOUNCE_MS);
  in.ignition = ignition_.value;
  in.pir_motion = digitalRead(Pins::PIR) == HIGH;
  in.count_delta = counter_.update(ir1_.value, ir2_.value, in.now_ms);
}
