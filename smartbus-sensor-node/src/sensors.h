#pragma once
#include "passenger_counter.h"
#include "types.h"
class Sensors {
public:
  void begin();
  void read(Inputs &in);

private:
  struct Debouncer {
    bool raw = false, value = false;
    uint32_t at = 0;
    bool update(bool next, uint32_t now, uint32_t interval);
  };
  Debouncer ir1_, ir2_, ignition_, safety_;
  PassengerCounter counter_;
};
