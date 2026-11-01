#include "actuators.h"
#include "display.h"
#include "mqtt_client.h"
#include "net_manager.h"
#include "secrets.h"
#include "sensors.h"
#include "state_machine.h"
#include <Arduino.h>
#include <WiFi.h>
#include <esp_task_wdt.h>
static Sensors sensors;
static StateMachine machine(BUS_ID);
static Actuators actuators;
static Display display;
static SensorMqtt mqtt;
void setup() {
  Serial.begin(Config::SERIAL_BAUD);
  Serial.printf("SmartBus fw=%s\n", Config::FW_VERSION);
  actuators.begin();
  sensors.begin();
  display.begin();
  mqtt.begin();
  esp_task_wdt_init(Config::WDT_S, true);
  esp_task_wdt_add(nullptr);
}
void loop() {
  Inputs in;
  in.now_ms = millis();
  in.epoch_ms = NetManager::epochMs();
  sensors.read(in);
  mqtt.receive(in);
  const Outputs &out = machine.update(in);
  actuators.update(out, in.now_ms);
  mqtt.publish(in, out);
  display.update(out, in.now_ms, WiFi.status() == WL_CONNECTED, mqtt.online());
  esp_task_wdt_reset();
  delay(Config::LOOP_MS);
}
