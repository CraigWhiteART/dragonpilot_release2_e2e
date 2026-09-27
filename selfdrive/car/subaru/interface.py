#!/usr/bin/env python3
from cereal import car
from panda import Panda
from selfdrive.car import STD_CARGO_KG, get_safety_config
from selfdrive.car.interfaces import CarInterfaceBase
from selfdrive.car.subaru.values import CAR, GLOBAL_GEN2, PREGLOBAL_CARS
from common.params import Params

# Early Global-platform Impreza/Crosstrek EPS firmware variants measured by the
# community to have ~0.18 s steering actuator delay. Keep this independent of
# steering torque limits: the C2 panda firmware in this fork still enforces the
# legacy Subaru safety configuration.
IMPREZA_2018_EPS_FW = {
  b'z\xc0\x00\x00',
  b'z\xc0\x04\x00',
  b'z\xc0\x08\x00',
  b'\x8a\xc0\x00\x00',
}

# Craig's detected EPS revision. Keep this separate from the community-tested
# 3071 allowlist above: no public evidence was found proving 7ac00a00 at 3071.
# It can only select the research Panda profile when the explicit param is set.
IMPREZA_HIGH_TORQUE_RESEARCH_EPS_FW = {
  b'z\xc0\n\x00',
}


class CarInterface(CarInterfaceBase):

  @staticmethod
  def _get_params(ret, candidate, fingerprint, car_fw, experimental_long):
    ret.carName = "subaru"
    ret.radarOffCan = True
    ret.dashcamOnly = candidate in PREGLOBAL_CARS
    ret.autoResumeSng = False

    if candidate in PREGLOBAL_CARS:
      ret.enableBsm = 0x25c in fingerprint[0]
      ret.safetyConfigs = [get_safety_config(car.CarParams.SafetyModel.subaruLegacy)]
    else:
      ret.enableBsm = 0x228 in fingerprint[0]
      ret.safetyConfigs = [get_safety_config(car.CarParams.SafetyModel.subaru)]
      if candidate in GLOBAL_GEN2:
        ret.safetyConfigs[0].safetyParam |= Panda.FLAG_SUBARU_GEN2

    ret.steerLimitTimer = 0.4
    ret.steerActuatorDelay = 0.1
    research_3071_defaults = False
    CarInterfaceBase.configure_torque_tune(candidate, ret.lateralTuning)

    if candidate == CAR.ASCENT:
      ret.mass = 2031. + STD_CARGO_KG
      ret.wheelbase = 2.89
      ret.centerToFront = ret.wheelbase * 0.5
      ret.steerRatio = 13.5
      ret.steerActuatorDelay = 0.3   # end-to-end angle controller
      ret.lateralTuning.init('pid')
      ret.lateralTuning.pid.kf = 0.00003
      ret.lateralTuning.pid.kiBP, ret.lateralTuning.pid.kpBP = [[0., 20.], [0., 20.]]
      ret.lateralTuning.pid.kpV, ret.lateralTuning.pid.kiV = [[0.0025, 0.1], [0.00025, 0.01]]

    elif candidate == CAR.IMPREZA:
      ret.mass = 1568. + STD_CARGO_KG
      ret.wheelbase = 2.67
      ret.centerToFront = ret.wheelbase * 0.5
      ret.steerRatio = 15
      ret.steerActuatorDelay = 0.4   # fallback for unclassified EPS firmware

      # Later Subaru community testing measured ~0.18 s actuator delay on these
      # 2017-19 Impreza / 2018-19 Crosstrek EPS variants. Using the measured
      # delay lets lateral control anticipate steering response more accurately
      # without increasing the Panda-enforced steering torque limit.
      if any((fw.ecu == "eps" or fw.ecu == car.CarParams.Ecu.eps) and fw.fwVersion in IMPREZA_2018_EPS_FW for fw in car_fw):
        ret.steerActuatorDelay = 0.18

      research_eps = any(
        (fw.ecu == "eps" or fw.ecu == car.CarParams.Ecu.eps) and fw.fwVersion in IMPREZA_HIGH_TORQUE_RESEARCH_EPS_FW
        for fw in car_fw
      )
      steer_stage_raw = Params().get("dp_toyota_cruise_override_speed", encoding="utf8")
      try:
        steer_stage = int(steer_stage_raw) if steer_stage_raw else 0
      except ValueError:
        steer_stage = 0
      steer_stage = max(0, min(steer_stage, 6))
      steer_research_enabled = Params().get_bool("dp_toyota_cruise_override")
      if steer_research_enabled and steer_stage > 0 and research_eps:
        # The matched research Panda safety profile is required for >2047.
        ret.safetyConfigs[0].safetyParam |= Panda.FLAG_SUBARU_MAX_STEER_IMPREZA_2018

        # The merged sunnypilot 3071 profile used the measured ~0.18 s delay
        # for this early Impreza/Crosstrek steering rack. Treat delay as a rack
        # characteristic, so use it for all explicitly-enabled research stages.
        ret.steerActuatorDelay = 0.18

        # The historical PID gains below were scaled for the full 3071 range.
        # Only apply them at stage 6; intermediate stages retain their existing
        # controller tune so staged authority comparisons remain interpretable.
        research_3071_defaults = steer_stage == 6

      ret.lateralTuning.init('pid')
      ret.lateralTuning.pid.kf = 0.00005
      ret.lateralTuning.pid.kiBP, ret.lateralTuning.pid.kpBP = [[0., 20.], [0., 20.]]
      ret.lateralTuning.pid.kpV, ret.lateralTuning.pid.kiV = [[0.2, 0.3], [0.02, 0.03]]

    elif candidate == CAR.IMPREZA_2020:
      ret.mass = 1480. + STD_CARGO_KG
      ret.wheelbase = 2.67
      ret.centerToFront = ret.wheelbase * 0.5
      ret.steerRatio = 17           # learned, 14 stock
      ret.lateralTuning.init('pid')
      ret.lateralTuning.pid.kf = 0.00005
      ret.lateralTuning.pid.kiBP, ret.lateralTuning.pid.kpBP = [[0., 14., 23.], [0., 14., 23.]]
      ret.lateralTuning.pid.kpV, ret.lateralTuning.pid.kiV = [[0.045, 0.042, 0.20], [0.04, 0.035, 0.045]]

    elif candidate == CAR.FORESTER:
      ret.mass = 1568. + STD_CARGO_KG
      ret.wheelbase = 2.67
      ret.centerToFront = ret.wheelbase * 0.5
      ret.steerRatio = 17           # learned, 14 stock
      ret.lateralTuning.init('pid')
      ret.lateralTuning.pid.kf = 0.000038
      ret.lateralTuning.pid.kiBP, ret.lateralTuning.pid.kpBP = [[0., 14., 23.], [0., 14., 23.]]
      ret.lateralTuning.pid.kpV, ret.lateralTuning.pid.kiV = [[0.01, 0.065, 0.2], [0.001, 0.015, 0.025]]

    elif candidate in (CAR.OUTBACK, CAR.LEGACY):
      ret.mass = 1568. + STD_CARGO_KG
      ret.wheelbase = 2.67
      ret.centerToFront = ret.wheelbase * 0.5
      ret.steerRatio = 17
      ret.steerActuatorDelay = 0.1
      CarInterfaceBase.configure_torque_tune(candidate, ret.lateralTuning)

    elif candidate in (CAR.FORESTER_PREGLOBAL, CAR.OUTBACK_PREGLOBAL_2018):
      ret.safetyConfigs[0].safetyParam = 1  # Outback 2018-2019 and Forester have reversed driver torque signal
      ret.mass = 1568 + STD_CARGO_KG
      ret.wheelbase = 2.67
      ret.centerToFront = ret.wheelbase * 0.5
      ret.steerRatio = 20           # learned, 14 stock

    elif candidate == CAR.LEGACY_PREGLOBAL:
      ret.mass = 1568 + STD_CARGO_KG
      ret.wheelbase = 2.67
      ret.centerToFront = ret.wheelbase * 0.5
      ret.steerRatio = 12.5   # 14.5 stock
      ret.steerActuatorDelay = 0.15

    elif candidate == CAR.OUTBACK_PREGLOBAL:
      ret.mass = 1568 + STD_CARGO_KG
      ret.wheelbase = 2.67
      ret.centerToFront = ret.wheelbase * 0.5
      ret.steerRatio = 20           # learned, 14 stock

    else:
      raise ValueError(f"unknown car: {candidate}")

    CarInterfaceBase.configure_dp_tune(candidate, ret.lateralTuning)

    # DragonPilot's controller selector runs after the car-specific block and
    # normally restores the legacy Impreza PID tune. Re-apply the documented
    # 3071-era PID scaling only when PID (Controller Type 1) is explicitly
    # selected. Torque (Type 3) remains untouched.
    if candidate == CAR.IMPREZA and research_3071_defaults and ret.lateralTuning.which() == 'pid':
      ret.lateralTuning.pid.kf = 0.00003333
      ret.lateralTuning.pid.kiBP, ret.lateralTuning.pid.kpBP = [[0., 20.], [0., 20.]]
      ret.lateralTuning.pid.kpV, ret.lateralTuning.pid.kiV = [[0.133, 0.2], [0.0133, 0.02]]

    Params().put("dp_lateral_steer_rate_cost", "0.7")
    return ret

  # returns a car.CarState
  def _update(self, c):

    ret = self.CS.update(self.cp, self.cp_cam, self.cp_body)

    ret.events = self.create_common_events(ret).to_msg()

    return ret

  def apply(self, c):
    return self.CC.update(c, self.CS)
