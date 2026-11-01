#include "../../src/passenger_counter.h"
#include "config.h"
#include <unity.h>
void setUp() {}
void tearDown() {}
void board_alight() {
  PassengerCounter c;
  TEST_ASSERT_EQUAL(0, c.update(true, false, 0));
  TEST_ASSERT_EQUAL(1, c.update(true, true, 100));
  TEST_ASSERT_EQUAL(0, c.update(true, true, 200));
  c.update(false, false, 300);
  c.update(false, true, 400);
  TEST_ASSERT_EQUAL(-1, c.update(true, true, 500));
}
void noise_timeout() {
  PassengerCounter c;
  c.update(true, false, 0);
  TEST_ASSERT_EQUAL(0, c.update(false, true, Config::IR_PAIR_WINDOW_MS + 1));
  c.update(false, false, 2000);
  TEST_ASSERT_EQUAL(0, c.update(true, true, 2100));
  TEST_ASSERT_EQUAL(0, c.update(false, true, 2200));
}
void boundary_and_wrap() {
  PassengerCounter c;
  c.update(true, false, UINT32_MAX - 500);
  TEST_ASSERT_EQUAL(1, c.update(false, true, 999));
  c.update(false, false, 1000);
  c.update(false, true, 2000);
  TEST_ASSERT_EQUAL(-1,
                    c.update(true, false, 2000 + Config::IR_PAIR_WINDOW_MS));
}
int main() {
  UNITY_BEGIN();
  RUN_TEST(board_alight);
  RUN_TEST(noise_timeout);
  RUN_TEST(boundary_and_wrap);
  return UNITY_END();
}
