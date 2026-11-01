#include "actuators.h"
#include "pins.h"
#include <Arduino.h>
void Actuators::begin() {
  digitalWrite(Pins::RELAY, !Config::RELAY_ACTIVE_LEVEL);
  for (int pin : {Pins::BUZZER, Pins::GREEN, Pins::RED, Pins::BLUE, Pins::RELAY})
    pinMode(pin, OUTPUT);
  digitalWrite(Pins::RELAY, !Config::RELAY_ACTIVE_LEVEL);
  digitalWrite(Pins::BUZZER, LOW);
  digitalWrite(Pins::GREEN, LOW);
  digitalWrite(Pins::RED, LOW);
  digitalWrite(Pins::BLUE, LOW);
}
void Actuators::update(const Outputs &o, uint32_t now) {
  bool buzz = o.buzzer_mode == BuzzerMode::CONTINUOUS ||
              o.buzzer_mode == BuzzerMode::ONE_SHOT_1S ||
              (o.buzzer_mode == BuzzerMode::INTERMITTENT &&
               (now / Config::BUZZER_HALF_MS) % 2 == 0);
  digitalWrite(Pins::BUZZER, buzz);
  // Common-cathode RGB: HIGH lights a channel. Blue is unused by alarm states.
  digitalWrite(Pins::BLUE, LOW);
  digitalWrite(Pins::GREEN, o.led == LedMode::GREEN);
  digitalWrite(Pins::RED,
               o.led == LedMode::RED || (o.led == LedMode::RED_BLINK &&
                                         (now / Config::LED_HALF_MS) % 2 == 0));
  digitalWrite(Pins::RELAY, o.fan_on ? Config::RELAY_ACTIVE_LEVEL
                                     : !Config::RELAY_ACTIVE_LEVEL);
}
