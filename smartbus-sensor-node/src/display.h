#pragma once
#include "types.h"
class Display {
public:
  void begin();
  void update(const Outputs &out, uint32_t now, bool wifi, bool mqtt);

private:
  uint32_t last_ = 0;
};
