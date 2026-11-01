#pragma once
#include "types.h"
class SensorMqtt {
public:
  void begin();
  void receive(Inputs &in);
  void publish(const Inputs &in, const Outputs &out);
  bool online() const;
};
