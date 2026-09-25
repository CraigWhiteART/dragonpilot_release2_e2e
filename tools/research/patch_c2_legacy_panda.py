#!/usr/bin/env python3
"""Reconstruct the C2-era DragonPilot Panda safety changes for research builds.

This script is intentionally applied to dragonpilot/panda commit
1d732d4747ea81c199906e9f1fc620911fb8add0 in CI. It does not flash hardware.

It preserves the stock Subaru profile (2047), preserves Subaru Gen2 (1000),
and adds a separately selected early-Impreza research profile (3071) using
safetyParam bit 2. All rate, realtime, and driver-torque limits are unchanged.

The C2 release also used DragonPilot's ALKA alternative-experience bit and an
extra usb_power_mode byte in the v11 health packet. The latter is retained as
an ABI compatibility placeholder in the research build.
"""

from pathlib import Path
import sys


ALT_MAX = 3071


def replace_once(path: Path, old: str, new: str) -> None:
  text = path.read_text()
  count = text.count(old)
  if count != 1:
    raise RuntimeError(f"{path}: expected exactly one match, found {count}")
  path.write_text(text.replace(old, new, 1))


def patch_health(root: Path) -> None:
  health = root / "board/health.h"
  replace_once(
    health,
    "  uint8_t fan_power;\n  uint8_t safety_rx_checks_invalid;\n};",
    "  uint8_t fan_power;\n  uint8_t safety_rx_checks_invalid;\n"
    "  // DragonPilot C2 v2023.02.08 Python ABI compatibility field.\n"
    "  uint8_t usb_power_mode;\n};",
  )

  comms = root / "board/main_comms.h"
  replace_once(
    comms,
    "  health->safety_rx_checks_invalid = safety_rx_checks_invalid;\n",
    "  health->safety_rx_checks_invalid = safety_rx_checks_invalid;\n"
    "  // The stripped C2 release exposed this byte in health v11. The public\n"
    "  // reconstruction does not have the private board power-state source, so\n"
    "  // keep the packet layout compatible and report the neutral value.\n"
    "  health->usb_power_mode = 0U;\n",
  )


def patch_alka(root: Path) -> None:
  decl = root / "board/safety_declarations.h"
  replace_once(
    decl,
    "#define ALT_EXP_RAISE_LONGITUDINAL_LIMITS_TO_ISO_MAX 8\n\nint alternative_experience = 0;",
    "#define ALT_EXP_RAISE_LONGITUDINAL_LIMITS_TO_ISO_MAX 8\n\n"
    "// DragonPilot always-lateral-control alternative experience.\n"
    "#define ALT_EXP_ALKA 16\n\n"
    "int alternative_experience = 0;",
  )

  safety = root / "board/safety.h"

  torque_old = """bool steer_torque_cmd_checks(int desired_torque, int steer_req, const SteeringLimits limits) {
  bool violation = false;
  uint32_t ts = microsecond_timer_get();

  if (controls_allowed) {"""
  torque_new = """bool steer_torque_cmd_checks(int desired_torque, int steer_req, const SteeringLimits limits) {
  bool violation = false;
  uint32_t ts = microsecond_timer_get();
  bool alka_enabled = alternative_experience & ALT_EXP_ALKA;

  if (controls_allowed || alka_enabled) {"""
  replace_once(safety, torque_old, torque_new)

  replace_once(
    safety,
    "  if (!controls_allowed && (desired_torque != 0)) {\n",
    "  if ((!controls_allowed && !alka_enabled) && (desired_torque != 0)) {\n",
  )

  replace_once(
    safety,
    "  if (violation || !controls_allowed) {\n",
    "  if (violation || (!controls_allowed && !alka_enabled)) {\n",
  )

  angle_old = """bool steer_angle_cmd_checks(int desired_angle, bool steer_control_enabled, const SteeringLimits limits) {
  bool violation = false;

  if (controls_allowed && steer_control_enabled) {"""
  angle_new = """bool steer_angle_cmd_checks(int desired_angle, bool steer_control_enabled, const SteeringLimits limits) {
  bool violation = false;
  bool alka_enabled = alternative_experience & ALT_EXP_ALKA;

  if ((controls_allowed || alka_enabled) && steer_control_enabled) {"""
  replace_once(safety, angle_old, angle_new)

  replace_once(
    safety,
    "  violation |= (!controls_allowed &&\n"
    "                  ((desired_angle < (angle_meas.min - 1)) ||\n"
    "                  (desired_angle > (angle_meas.max + 1))));",
    "  violation |= ((!controls_allowed && !alka_enabled) &&\n"
    "                  ((desired_angle < (angle_meas.min - 1)) ||\n"
    "                  (desired_angle > (angle_meas.max + 1))));",
  )

  replace_once(
    safety,
    "  violation |= !controls_allowed && steer_control_enabled;",
    "  violation |= (!controls_allowed && !alka_enabled) && steer_control_enabled;",
  )


def patch_subaru(root: Path) -> None:
  path = root / "board/safety/safety_subaru.h"

  stock_limits = """const SteeringLimits SUBARU_STEERING_LIMITS = {
  .max_steer = 2047,
  .max_rt_delta = 940,
  .max_rt_interval = 250000,
  .max_rate_up = 50,
  .max_rate_down = 70,
  .driver_torque_factor = 50,
  .driver_torque_allowance = 60,
  .type = TorqueDriverLimited,
};
"""
  alt_limits = stock_limits + f"""
// Historical early-Impreza/Crosstrek alternate command ceiling.
// This profile is selected only with safetyParam bit 2.
const SteeringLimits SUBARU_STEERING_LIMITS_IMPREZA_2018 = {{
  .max_steer = {ALT_MAX},
  .max_rt_delta = 940,
  .max_rt_interval = 250000,
  .max_rate_up = 50,
  .max_rate_down = 70,
  .driver_torque_factor = 50,
  .driver_torque_allowance = 60,
  .type = TorqueDriverLimited,
}};
"""
  replace_once(path, stock_limits, alt_limits)

  replace_once(
    path,
    "const uint16_t SUBARU_PARAM_GEN2 = 1;\nbool subaru_gen2 = false;",
    "const uint16_t SUBARU_PARAM_GEN2 = 1;\n"
    "const uint16_t SUBARU_PARAM_MAX_STEER_IMPREZA_2018 = 2;\n"
    "bool subaru_gen2 = false;\n"
    "bool subaru_max_steer_impreza_2018 = false;",
  )

  replace_once(
    path,
    "    const SteeringLimits limits = subaru_gen2 ? SUBARU_GEN2_STEERING_LIMITS : SUBARU_STEERING_LIMITS;",
    "    const SteeringLimits limits = subaru_gen2 ? SUBARU_GEN2_STEERING_LIMITS :\n"
    "      (subaru_max_steer_impreza_2018 ? SUBARU_STEERING_LIMITS_IMPREZA_2018 : SUBARU_STEERING_LIMITS);",
  )

  replace_once(
    path,
    "static const addr_checks* subaru_init(uint16_t param) {\n  subaru_gen2 = GET_FLAG(param, SUBARU_PARAM_GEN2);",
    "static const addr_checks* subaru_init(uint16_t param) {\n"
    "  subaru_gen2 = GET_FLAG(param, SUBARU_PARAM_GEN2);\n"
    "  subaru_max_steer_impreza_2018 = GET_FLAG(param, SUBARU_PARAM_MAX_STEER_IMPREZA_2018);",
  )


def patch_python_api(root: Path) -> None:
  path = root / "python/__init__.py"
  replace_once(
    path,
    "  RAISE_LONGITUDINAL_LIMITS_TO_ISO_MAX = 8\n",
    "  RAISE_LONGITUDINAL_LIMITS_TO_ISO_MAX = 8\n"
    "  ALKA = 16\n",
  )
  replace_once(
    path,
    "  FLAG_SUBARU_GEN2 = 1\n",
    "  FLAG_SUBARU_GEN2 = 1\n"
    "  FLAG_SUBARU_MAX_STEER_IMPREZA_2018 = 2\n",
  )

  # Match the stripped v2023.02.08 C2 health packet ABI.
  replace_once(
    path,
    '  HEALTH_STRUCT = struct.Struct("<IIIIIIIIIBBBBBBHBBBHfBB")',
    '  HEALTH_STRUCT = struct.Struct("<IIIIIIIIIBBBBBBHBBBHfBBB")',
  )
  replace_once(
    path,
    '      "safety_rx_checks_invalid": a[22],\n',
    '      "safety_rx_checks_invalid": a[22],\n'
    '      "usb_power_mode": a[23],\n',
  )


def patch_tests(root: Path) -> None:
  path = root / "tests/safety/test_subaru.py"

  insert = """

class TestSubaruMaxSteer2018Safety(TestSubaruSafety):
  # Separate safetyParam=2 profile. Stock Subaru remains 2047.
  MAX_TORQUE = 3071

  def setUp(self):
    self.packer = CANPackerPanda("subaru_global_2017_generated")
    self.safety = libpanda_py.libpanda
    self.safety.set_safety_hooks(Panda.SAFETY_SUBARU, Panda.FLAG_SUBARU_MAX_STEER_IMPREZA_2018)
    self.safety.init_tests()

"""
  replace_once(path, "\n\nclass TestSubaruGen2Safety(TestSubaruSafety):", insert + "\nclass TestSubaruGen2Safety(TestSubaruSafety):")

  # Verify the C2 DragonPilot ALKA behavior itself rather than merely compiling it.
  replace_once(
    path,
    "  def _set_prev_torque(self, t):\n"
    "    self.safety.set_desired_torque_last(t)\n"
    "    self.safety.set_rt_torque_last(t)\n",
    "  def _set_prev_torque(self, t):\n"
    "    self.safety.set_desired_torque_last(t)\n"
    "    self.safety.set_rt_torque_last(t)\n"
    "\n"
    "  def test_dragonpilot_alka_lateral_without_cruise(self):\n"
    "    self.safety.set_controls_allowed(False)\n"
    "    self.safety.set_alternative_experience(16)\n"
    "    self.safety.set_torque_driver(0, 0)\n"
    "    self._set_prev_torque(0)\n"
    "    self.assertTrue(self._tx(self._torque_cmd_msg(self.MAX_RATE_UP)))\n"
    "\n"
    "    self.safety.set_alternative_experience(0)\n"
    "    self._set_prev_torque(0)\n"
    "    self.assertFalse(self._tx(self._torque_cmd_msg(self.MAX_RATE_UP)))\n",
  )


def validate(root: Path) -> None:
  subaru = (root / "board/safety/safety_subaru.h").read_text()
  py = (root / "python/__init__.py").read_text()
  health = (root / "board/health.h").read_text()
  tests = (root / "tests/safety/test_subaru.py").read_text()

  assert ".max_steer = 2047" in subaru
  assert f".max_steer = {ALT_MAX}" in subaru
  assert ".max_steer = 1000" in subaru
  assert "SUBARU_PARAM_MAX_STEER_IMPREZA_2018 = 2" in subaru
  assert "FLAG_SUBARU_MAX_STEER_IMPREZA_2018 = 2" in py
  assert "ALKA = 16" in py
  assert 'HEALTH_STRUCT = struct.Struct("<IIIIIIIIIBBBBBBHBBBHfBBB")' in py
  assert "uint8_t usb_power_mode;" in health
  assert "MAX_TORQUE = 3071" in tests

  # The alternate profile must not relax the existing dynamic safety constraints.
  alt = subaru.split("SUBARU_STEERING_LIMITS_IMPREZA_2018", 1)[1].split("};", 1)[0]
  for required in (
    ".max_rt_delta = 940",
    ".max_rt_interval = 250000",
    ".max_rate_up = 50",
    ".max_rate_down = 70",
    ".driver_torque_factor = 50",
    ".driver_torque_allowance = 60",
    ".type = TorqueDriverLimited",
  ):
    assert required in alt, required


def main() -> None:
  if len(sys.argv) != 2:
    raise SystemExit(f"usage: {sys.argv[0]} /path/to/panda")

  root = Path(sys.argv[1]).resolve()
  if not (root / "board/safety/safety_subaru.h").exists():
    raise SystemExit(f"not a Panda source tree: {root}")

  patch_health(root)
  patch_alka(root)
  patch_subaru(root)
  patch_python_api(root)
  patch_tests(root)
  validate(root)
  print(f"Patched legacy Panda research tree at {root}")
  print(f"Experimental Subaru max: {ALT_MAX}")
  print("Stock Subaru max remains: 2047")


if __name__ == "__main__":
  main()
