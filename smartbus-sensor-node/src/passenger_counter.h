#pragma once
#include <cstdint>
class PassengerCounter {
public:
  int update(bool ir1, bool ir2, uint32_t now_ms);

private:
  enum class Phase { IDLE, FIRST_OUTER, FIRST_INNER, WAIT_CLEAR };
  Phase phase_ = Phase::IDLE;
  uint32_t started_ = 0;
};
