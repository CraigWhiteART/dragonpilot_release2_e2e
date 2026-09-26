#!/usr/bin/env python3
"""Dependency-free steering safety checks for the reconstructed C2 Panda.

Run from the Panda source tree after `scons` has built tests/libpanda/libpanda.so.
This intentionally avoids opendbc/CANPacker so legacy build plumbing cannot mask
the actual Subaru steering safety assertions.
"""

from panda import Panda
from panda.tests.libpanda import libpanda_py


SAFETY_SUBARU = Panda.SAFETY_SUBARU
FLAG_RESEARCH = Panda.FLAG_SUBARU_MAX_STEER_IMPREZA_2018


def es_lkas(torque):
  # safety_subaru.h decodes:
  #   raw = (GET_BYTES_04(msg) >> 16) & 0x1fff
  #   desired_torque = -to_signed(raw, 13)
  raw = (-int(torque)) & 0x1FFF
  dat = bytes((0, 0, raw & 0xFF, (raw >> 8) & 0x1F, 0, 0, 0, 0))
  return libpanda_py.make_CANPacket(0x122, 0, dat)


def reset(profile):
  s = libpanda_py.libpanda
  assert s.set_safety_hooks(SAFETY_SUBARU, profile) == 0
  s.init_tests()
  s.set_controls_allowed(True)
  s.set_torque_driver(0, 0)
  return s


def set_prev(s, torque):
  s.set_desired_torque_last(torque)
  s.set_rt_torque_last(torque)


def tx_at(s, torque):
  set_prev(s, torque)
  return bool(s.safety_tx_hook(es_lkas(torque)))


def main():
  # Stock safety profile remains exactly 2047.
  s = reset(0)
  assert tx_at(s, 2047), "stock profile rejected 2047"
  s.set_controls_allowed(True)
  assert not tx_at(s, 2048), "stock profile allowed 2048"
  s.set_controls_allowed(True)
  assert not tx_at(s, 3071), "stock profile allowed 3071"

  # Research safetyParam=2 raises only the absolute envelope to 3071.
  s = reset(FLAG_RESEARCH)
  assert tx_at(s, 2047), "research profile rejected legacy 2047"
  s.set_controls_allowed(True)
  assert tx_at(s, 2300), "research profile rejected staged 2300"
  s.set_controls_allowed(True)
  assert tx_at(s, 2800), "research profile rejected staged 2800"
  s.set_controls_allowed(True)
  assert tx_at(s, 3071), "research profile rejected 3071"
  s.set_controls_allowed(True)
  assert not tx_at(s, 3072), "research profile allowed 3072"

  # Existing slew-up protection remains 50 units per control step.
  s = reset(FLAG_RESEARCH)
  set_prev(s, 0)
  assert s.safety_tx_hook(es_lkas(50)), "rate-up limit rejected +50"
  s = reset(FLAG_RESEARCH)
  set_prev(s, 0)
  assert not s.safety_tx_hook(es_lkas(51)), "rate-up limit allowed +51"
  s = reset(FLAG_RESEARCH)
  set_prev(s, 0)
  assert s.safety_tx_hook(es_lkas(-50)), "rate-up limit rejected -50"
  s = reset(FLAG_RESEARCH)
  set_prev(s, 0)
  assert not s.safety_tx_hook(es_lkas(-51)), "rate-up limit allowed -51"

  # Driver override protection remains active. This mirrors the upstream
  # DriverTorqueSteeringSafetyTest boundary: allowance is 60.
  s = reset(FLAG_RESEARCH)
  s.set_torque_driver(60, 60)
  set_prev(s, -3071)
  assert s.safety_tx_hook(es_lkas(-3071)), "driver allowance boundary rejected"

  s = reset(FLAG_RESEARCH)
  s.set_torque_driver(61, 61)
  set_prev(s, -3071)
  assert not s.safety_tx_hook(es_lkas(-3071)), "driver torque protection relaxed"

  # Torque must still be zero when controls are off unless DragonPilot ALKA is
  # explicitly active.
  s = reset(FLAG_RESEARCH)
  s.set_controls_allowed(False)
  set_prev(s, 0)
  assert not s.safety_tx_hook(es_lkas(1)), "nonzero torque allowed while controls off"

  print("PASS: stock Subaru max remains 2047")
  print("PASS: research safetyParam=2 allows through 3071 and rejects 3072")
  print("PASS: max_rate_up remains 50")
  print("PASS: driver torque allowance/protection remains active")
  print("PASS: controls-off torque remains blocked")


if __name__ == "__main__":
  main()
