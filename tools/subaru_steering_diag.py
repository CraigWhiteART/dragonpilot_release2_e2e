#!/usr/bin/env python3
"""Print the active Subaru steering configuration on a running C2.

Run from the openpilot/dragonpilot checkout:
  python3 tools/subaru_steering_diag.py
"""

from cereal import car
from common.params import Params
from selfdrive.car.subaru.values import CAR, CarControllerParams


KNOWN_3071_EPS_FW = {
  b'z\xc0\x00\x00',
  b'z\xc0\x04\x00',
  b'z\xc0\x08\x00',
  b'\x8a\xc0\x00\x00',
}


def get_param_text(params, key):
  value = params.get(key)
  if value is None:
    return "<unset>"
  try:
    return value.decode("utf-8")
  except Exception:
    return repr(value)


def is_eps_firmware(fw):
  try:
    if fw.ecu == "eps" or fw.ecu == car.CarParams.Ecu.eps:
      return True
  except Exception:
    pass
  return str(fw.ecu).lower().endswith("eps")


def main():
  params = Params()
  raw_cp = params.get("CarParams")
  if raw_cp is None:
    raise SystemExit("CarParams is not available. Run this on the C2 after the car has been detected.")

  CP = car.CarParams.from_bytes(raw_cp)
  controller = CarControllerParams(CP)

  print("Subaru steering diagnostics")
  print("==========================")
  print(f"carFingerprint:       {CP.carFingerprint}")
  print(f"carName:              {CP.carName}")
  print(f"STEER_MAX:            {controller.STEER_MAX}")
  print(f"STEER_DELTA_UP:       {controller.STEER_DELTA_UP}")
  print(f"STEER_DELTA_DOWN:     {controller.STEER_DELTA_DOWN}")
  print(f"steerRatio:           {CP.steerRatio}")
  print(f"steerActuatorDelay:   {CP.steerActuatorDelay}")
  print(f"steerLimitTimer:      {CP.steerLimitTimer}")

  try:
    print(f"lateralTuning:        {CP.lateralTuning.which()}")
  except Exception:
    print("lateralTuning:        <unknown>")

  print(f"dp_lateral_tune:      {get_param_text(params, 'dp_lateral_tune')}")
  print(f"dp_steer_rate_cost:   {get_param_text(params, 'dp_lateral_steer_rate_cost')}")

  if len(CP.safetyConfigs):
    for i, cfg in enumerate(CP.safetyConfigs):
      print(f"safety[{i}].model:      {cfg.safetyModel}")
      print(f"safety[{i}].param:      {cfg.safetyParam}")

  eps_fw = []
  for fw in CP.carFw:
    if is_eps_firmware(fw):
      version = bytes(fw.fwVersion)
      eps_fw.append(version)
      print(f"EPS firmware:         {version.hex(' ')}  ({version!r})")

  if not eps_fw:
    print("EPS firmware:         <not present in cached CarParams>")

  known_high_torque_eps = any(version in KNOWN_3071_EPS_FW for version in eps_fw)
  print(f"known 3071-era EPS:   {'YES' if known_high_torque_eps else 'no/unknown'}")

  if CP.carFingerprint == CAR.IMPREZA:
    if known_high_torque_eps:
      print("")
      print("This EPS is in the community-tested early Impreza/Crosstrek 3071 firmware list.")
      print("This C2 fork still uses the legacy Panda safety firmware, so the active steering")
      print("ceiling remains the STEER_MAX printed above unless Panda safety is upgraded too.")
    else:
      print("")
      print("This is the 2017-19 Impreza/Crosstrek platform, but the cached EPS firmware")
      print("did not match the known community-tested 3071 firmware list.")


if __name__ == "__main__":
  main()
