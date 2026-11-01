#pragma once
#include "types.h"
class Actuators {
public:
  void begin();
  void update(const Outputs &out, uint32_t now);
};
