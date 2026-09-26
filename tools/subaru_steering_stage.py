#!/usr/bin/env python3
"""Read or set the staged Subaru steering-authority research value.

Usage:
  python3 tools/subaru_steering_stage.py
  python3 tools/subaru_steering_stage.py 2047
  python3 tools/subaru_steering_stage.py 2300

A restart is required before CarParams/CarControllerParams use a changed stage.
"""

import sys

from common.params import Params
from selfdrive.car.subaru.values import SUBARU_STEER_MAX_STAGES


PARAM = "dp_toyota_cruise_override_speed"
ENABLE_PARAM = "dp_toyota_cruise_override"


def current_stage(params):
  raw = params.get(PARAM, encoding="utf8")
  if not raw:
    return 0
  try:
    stage = int(raw)
  except ValueError:
    stage = 0
  return max(0, min(stage, len(SUBARU_STEER_MAX_STAGES) - 1))


def main():
  params = Params()

  if len(sys.argv) == 1:
    stage = current_stage(params)
    print("stage:", stage)
    print("STEER_MAX:", SUBARU_STEER_MAX_STAGES[stage])
    print("enabled:", params.get_bool(ENABLE_PARAM))
    print("choices:", ", ".join(map(str, SUBARU_STEER_MAX_STAGES)))
    return

  if len(sys.argv) != 2:
    raise SystemExit("usage: subaru_steering_stage.py [2047|2150|2300|2450|2600|2800|3071]")

  try:
    requested = int(sys.argv[1])
  except ValueError:
    raise SystemExit("stage value must be an integer")

  if requested not in SUBARU_STEER_MAX_STAGES:
    raise SystemExit("allowed values: " + ", ".join(map(str, SUBARU_STEER_MAX_STAGES)))

  stage = SUBARU_STEER_MAX_STAGES.index(requested)
  params.put(PARAM, str(stage))
  params.put_bool(ENABLE_PARAM, requested != 2047)

  print("research enabled:", requested != 2047)
  print("set stage:", stage)
  print("STEER_MAX:", requested)
  print("Restart required for the new stage to become active.")


if __name__ == "__main__":
  main()
