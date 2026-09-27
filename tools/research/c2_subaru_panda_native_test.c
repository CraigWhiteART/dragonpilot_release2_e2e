// Dependency-free native safety test for the reconstructed C2 Panda.
// Compile from a patched legacy Panda source tree with:
//   gcc -std=gnu11 -O0 -Itests/libpanda -Iboard \
//     /path/to/this/file.c -o /tmp/c2_subaru_panda_native_test
//
// The test includes libpanda's native safety harness directly, so it exercises
// the same safety_tx_hook used by Panda unit tests without requiring opendbc.

#include <assert.h>
#include <stdio.h>

#include "tests/libpanda/panda.c"

#define SUBARU_SAFETY_MODE 11U
#define SUBARU_RESEARCH_PARAM 2U

static CANPacket_t es_lkas(int torque) {
  CANPacket_t msg = {0};
  msg.addr = 0x122U;
  msg.bus = 0U;
  msg.data_len_code = 8U;

  // safety_subaru.h:
  // raw = (GET_BYTES_04(msg) >> 16) & 0x1FFF
  // desired_torque = -to_signed(raw, 13)
  unsigned int raw = ((unsigned int)(-torque)) & 0x1FFFU;
  msg.data[2] = raw & 0xFFU;
  msg.data[3] = (raw >> 8U) & 0x1FU;
  return msg;
}

static void reset_profile(unsigned int param) {
  assert(set_safety_hooks(SUBARU_SAFETY_MODE, param) == 0);
  init_tests();
  set_controls_allowed(true);
  set_torque_driver(0, 0);
}

static void set_prev(int torque) {
  set_desired_torque_last(torque);
  set_rt_torque_last(torque);
}

static int tx_at(int torque) {
  CANPacket_t msg = es_lkas(torque);
  set_prev(torque);
  return safety_tx_hook(&msg);
}

int main(void) {
  // Stock profile: 2047 is the absolute ceiling.
  reset_profile(0U);
  assert(tx_at(2047) == 1);
  set_controls_allowed(true);
  assert(tx_at(2048) == 0);
  set_controls_allowed(true);
  assert(tx_at(3071) == 0);

  // Research profile: absolute ceiling is 3071.
  reset_profile(SUBARU_RESEARCH_PARAM);
  assert(tx_at(2047) == 1);
  set_controls_allowed(true);
  assert(tx_at(2150) == 1);
  set_controls_allowed(true);
  assert(tx_at(2300) == 1);
  set_controls_allowed(true);
  assert(tx_at(2450) == 1);
  set_controls_allowed(true);
  assert(tx_at(2600) == 1);
  set_controls_allowed(true);
  assert(tx_at(2800) == 1);
  set_controls_allowed(true);
  assert(tx_at(3071) == 1);
  set_controls_allowed(true);
  assert(tx_at(3072) == 0);

  // Slew-up remains 50 per steering command step.
  reset_profile(SUBARU_RESEARCH_PARAM);
  set_prev(0);
  CANPacket_t msg50 = es_lkas(50);
  assert(safety_tx_hook(&msg50) == 1);

  reset_profile(SUBARU_RESEARCH_PARAM);
  set_prev(0);
  CANPacket_t msg51 = es_lkas(51);
  assert(safety_tx_hook(&msg51) == 0);

  reset_profile(SUBARU_RESEARCH_PARAM);
  set_prev(0);
  CANPacket_t msg_n50 = es_lkas(-50);
  assert(safety_tx_hook(&msg_n50) == 1);

  reset_profile(SUBARU_RESEARCH_PARAM);
  set_prev(0);
  CANPacket_t msg_n51 = es_lkas(-51);
  assert(safety_tx_hook(&msg_n51) == 0);

  // Driver torque override protection remains unchanged.
  reset_profile(SUBARU_RESEARCH_PARAM);
  set_torque_driver(60, 60);
  set_prev(-3071);
  CANPacket_t max_neg = es_lkas(-3071);
  assert(safety_tx_hook(&max_neg) == 1);

  reset_profile(SUBARU_RESEARCH_PARAM);
  set_torque_driver(61, 61);
  set_prev(-3071);
  max_neg = es_lkas(-3071);
  assert(safety_tx_hook(&max_neg) == 0);

  // No non-zero steering while controls are off under normal experience.
  reset_profile(SUBARU_RESEARCH_PARAM);
  set_controls_allowed(false);
  set_prev(0);
  CANPacket_t one = es_lkas(1);
  assert(safety_tx_hook(&one) == 0);

  puts("PASS stock max=2047");
  puts("PASS research stages through max=3071; 3072 rejected");
  puts("PASS max_rate_up=50 retained");
  puts("PASS driver torque protection retained");
  puts("PASS controls-off torque blocked");
  return 0;
}
