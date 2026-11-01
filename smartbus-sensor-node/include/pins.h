#pragma once
namespace Pins {
constexpr int IR1 = 4, IR2 = 6, PIR = 5, IGNITION = 7, SAFETY = 11;
constexpr int BUZZER = 12, GREEN = 15, RED = 14, BLUE = 16, RELAY = 13, SDA = 8, SCL = 9;
} // namespace Pins

static_assert(Pins::SAFETY != Pins::GREEN && Pins::SAFETY != Pins::RED && Pins::SAFETY != Pins::BLUE, "Safety must not share an RGB output");
