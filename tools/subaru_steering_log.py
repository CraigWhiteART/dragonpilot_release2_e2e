#!/usr/bin/env python3
"""Persist Subaru lateral-control data across C2 reboots/power loss.

Run while parked before a normal drive:
  nohup python3 tools/subaru_steering_log.py >/data/subaru_steering_logger.out 2>&1 &

Logs are written to /data/subaru_steering_logs as CSV and fsync'd once per
second so an unexpected shutdown should lose at most the most recent samples.
"""

import csv
import os
import signal
import sys
import time
from datetime import datetime

import cereal.messaging as messaging


LOG_DIR = "/data/subaru_steering_logs"
SAMPLE_PERIOD = 0.05  # 20 Hz
FSYNC_PERIOD = 1.0


def _enum_name(value):
  try:
    return str(value)
  except Exception:
    return ""


def main():
  os.makedirs(LOG_DIR, exist_ok=True)
  stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
  path = os.path.join(LOG_DIR, "subaru_steering_%s.csv" % stamp)
  latest_path = os.path.join(LOG_DIR, "LATEST")

  sm = messaging.SubMaster(["carState", "carControl", "controlsState"])

  fields = [
    "unix_time",
    "mono_time",
    "v_ego_kph",
    "steering_angle_deg",
    "steering_rate_deg_s",
    "driver_torque",
    "eps_torque",
    "steering_pressed",
    "lat_active",
    "requested_steer",
    "output_steer",
    "steer_output_can",
    "controls_enabled",
    "controls_active",
    "lateral_state",
    "lat_saturated",
    "lat_output",
    "desired_steering_angle_deg",
    "angle_error_deg",
    "pid_p",
    "pid_i",
    "pid_f",
    "actual_lateral_accel",
    "desired_lateral_accel",
    "desired_curvature",
    "desired_curvature_rate",
    "steer_fault_temporary",
    "steer_fault_permanent",
  ]

  stop = [False]

  def request_stop(signum, frame):
    stop[0] = True

  signal.signal(signal.SIGTERM, request_stop)
  signal.signal(signal.SIGINT, request_stop)

  with open(path, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    f.flush()
    os.fsync(f.fileno())

    with open(latest_path, "w") as latest:
      latest.write(path + "\n")
      latest.flush()
      os.fsync(latest.fileno())

    print("Logging Subaru steering data to:", path)
    print("Sampling at ~20 Hz; fsync every 1 second.")
    sys.stdout.flush()

    last_sample = 0.0
    last_sync = time.monotonic()

    while not stop[0]:
      sm.update(100)
      now = time.monotonic()
      if now - last_sample < SAMPLE_PERIOD:
        continue
      last_sample = now

      CS = sm["carState"]
      CC = sm["carControl"]
      controls = sm["controlsState"]

      lateral_state = ""
      lat_saturated = False
      lat_output = 0.0
      desired_steering_angle_deg = 0.0
      angle_error_deg = 0.0
      pid_p = 0.0
      pid_i = 0.0
      pid_f = 0.0
      actual_lat_accel = 0.0
      desired_lat_accel = 0.0

      try:
        lateral_state = controls.lateralControlState.which()
        if lateral_state == "torqueState":
          torque = controls.lateralControlState.torqueState
          lat_saturated = bool(torque.saturated)
          lat_output = float(torque.output)
          actual_lat_accel = float(torque.actualLateralAccel)
          desired_lat_accel = float(torque.desiredLateralAccel)
        elif lateral_state == "pidState":
          state = controls.lateralControlState.pidState
          lat_saturated = bool(state.saturated)
          lat_output = float(state.output)
          desired_steering_angle_deg = float(state.steeringAngleDesiredDeg)
          angle_error_deg = float(state.angleError)
          pid_p = float(state.p)
          pid_i = float(state.i)
          pid_f = float(state.f)
        elif lateral_state == "lqrState":
          state = controls.lateralControlState.lqrState
          lat_saturated = bool(state.saturated)
          lat_output = float(state.output)
        elif lateral_state == "angleState":
          state = controls.lateralControlState.angleState
          lat_saturated = bool(state.saturated)
          lat_output = float(state.output)
      except Exception:
        pass

      writer.writerow({
        "unix_time": "%.3f" % time.time(),
        "mono_time": "%.3f" % now,
        "v_ego_kph": "%.3f" % (float(CS.vEgo) * 3.6),
        "steering_angle_deg": "%.4f" % float(CS.steeringAngleDeg),
        "steering_rate_deg_s": "%.4f" % float(CS.steeringRateDeg),
        "driver_torque": "%.4f" % float(CS.steeringTorque),
        "eps_torque": "%.4f" % float(CS.steeringTorqueEps),
        "steering_pressed": int(bool(CS.steeringPressed)),
        "lat_active": int(bool(CC.latActive)),
        "requested_steer": "%.6f" % float(CC.actuators.steer),
        "output_steer": "%.6f" % float(CC.actuatorsOutput.steer),
        "steer_output_can": "%.3f" % float(CC.actuatorsOutput.steerOutputCan),
        "controls_enabled": int(bool(controls.enabled)),
        "controls_active": int(bool(controls.active)),
        "lateral_state": lateral_state,
        "lat_saturated": int(bool(lat_saturated)),
        "lat_output": "%.6f" % lat_output,
        "desired_steering_angle_deg": "%.4f" % desired_steering_angle_deg,
        "angle_error_deg": "%.4f" % angle_error_deg,
        "pid_p": "%.6f" % pid_p,
        "pid_i": "%.6f" % pid_i,
        "pid_f": "%.6f" % pid_f,
        "actual_lateral_accel": "%.6f" % actual_lat_accel,
        "desired_lateral_accel": "%.6f" % desired_lat_accel,
        "desired_curvature": "%.8f" % float(controls.desiredCurvature),
        "desired_curvature_rate": "%.8f" % float(controls.desiredCurvatureRate),
        "steer_fault_temporary": int(bool(CS.steerFaultTemporary)),
        "steer_fault_permanent": int(bool(CS.steerFaultPermanent)),
      })

      if now - last_sync >= FSYNC_PERIOD:
        f.flush()
        os.fsync(f.fileno())
        last_sync = now

    f.flush()
    os.fsync(f.fileno())

  print("Stopped. Log saved:", path)


if __name__ == "__main__":
  main()
