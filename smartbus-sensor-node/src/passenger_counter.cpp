#include "passenger_counter.h"
#include "config.h"
int PassengerCounter::update(bool a, bool b, uint32_t now) {
  if (phase_ == Phase::WAIT_CLEAR) {
    if (!a && !b)
      phase_ = Phase::IDLE;
    return 0;
  }
  if (phase_ == Phase::IDLE) {
    if (a && b)
      phase_ = Phase::WAIT_CLEAR;
    else if (a || b) {
      phase_ = a ? Phase::FIRST_OUTER : Phase::FIRST_INNER;
      started_ = now;
    }
    return 0;
  }
  if (uint32_t(now - started_) > Config::IR_PAIR_WINDOW_MS) {
    phase_ = (!a && !b) ? Phase::IDLE : Phase::WAIT_CLEAR;
    return 0;
  }
  if ((phase_ == Phase::FIRST_OUTER && b) ||
      (phase_ == Phase::FIRST_INNER && a)) {
    int delta = phase_ == Phase::FIRST_OUTER ? 1 : -1;
    phase_ = Phase::WAIT_CLEAR;
    return delta;
  }
  return 0;
}
