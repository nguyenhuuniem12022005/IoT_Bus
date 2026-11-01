#include "display.h"
#include "pins.h"
#include "secrets.h"
#include <U8g2lib.h>
#include <Wire.h>
namespace {
U8G2_SSD1306_128X64_NONAME_F_HW_I2C screen(U8G2_R0, U8X8_PIN_NONE);
struct Frame {
  State state;
  int ir_count;
  Presence presence;
  bool safety_confirmed;
  uint32_t grace_remaining_s;
  bool wifi;
  bool mqtt;
};
QueueHandle_t frames;
void displayTask(void *) {
  Wire.begin(Pins::SDA, Pins::SCL);
  Wire.setTimeOut(Config::I2C_TIMEOUT_MS);
  Wire.beginTransmission(Config::OLED_ADDRESS);
  bool ready = Wire.endTransmission() == 0;
  if (ready) {
    screen.setI2CAddress(Config::OLED_ADDRESS << 1);
    screen.begin();
    screen.setFont(u8g2_font_5x7_tf);
  }
  Frame o{};
  for (;;) {
    // Chờ dữ liệu ở task riêng; I2C không chặn đọc cảm biến hay cập nhật còi.
    if (xQueueReceive(frames, &o, portMAX_DELAY) != pdTRUE || !ready)
      continue;
    char line[96];
    screen.clearBuffer();
    snprintf(line, sizeof(line), "%s %s", BUS_ID, stateName(o.state));
    screen.drawStr(0, 10, line);
    snprintf(line, sizeof(line), "IR: %d", o.ir_count);
    screen.drawStr(0, 23, line);
    snprintf(line, sizeof(line), "P:%d%d%d SAFETY:%s", o.presence.pir,
             o.presence.ir, o.presence.vision,
             o.safety_confirmed ? "DA" : "CHUA");
    screen.drawStr(0, 36, line);
    snprintf(line, sizeof(line), "W:%d M:%d CON:%lus", o.wifi, o.mqtt,
             static_cast<unsigned long>(o.grace_remaining_s));
    screen.drawStr(0, 49, line);
    if (o.state == State::CHECKING && !o.grace_remaining_s)
      screen.drawStr(0, 62, "BAM SAFETY");
    screen.sendBuffer();
  }
}
} // namespace
void Display::begin() {
  frames = xQueueCreate(1, sizeof(Frame));
  configASSERT(frames);
  BaseType_t result =
      xTaskCreatePinnedToCore(displayTask, "smartbus-oled",
                              Config::DISPLAY_STACK, nullptr, 1, nullptr, 0);
  configASSERT(result == pdPASS);
}
void Display::update(const Outputs &o, uint32_t now, bool wifi, bool mqtt) {
  if (uint32_t(now - last_) < Config::DISPLAY_MS)
    return;
  last_ = now;
  Frame frame{
      o.state, o.ir_count, o.presence, o.safety_confirmed, o.grace_remaining_s,
      wifi,    mqtt};
  xQueueOverwrite(frames, &frame);
}
