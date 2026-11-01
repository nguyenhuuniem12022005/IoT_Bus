#pragma once
#include <cstdint>
class NetManager {
public:
  void begin();
  void update(uint32_t now);
  static uint64_t epochMs();

private:
  uint32_t last_ = 0, backoff_ = 0;
  bool was_online_ = false;
};
