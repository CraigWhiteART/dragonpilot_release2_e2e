#!/usr/bin/env python3
"""Summarize a Subaru steering CSV captured by subaru_steering_log.py.

Examples:
  python3 tools/analyze_subaru_steering_log.py
  python3 tools/analyze_subaru_steering_log.py /data/subaru_steering_logs/subaru_steering_....csv
  python3 tools/analyze_subaru_steering_log.py --steer-max 2300

With no path, the logger's /data/subaru_steering_logs/LATEST pointer is used.
"""

import argparse
import csv
import math
import os
from statistics import mean

LOG_DIR = "/data/subaru_steering_logs"
LATEST = os.path.join(LOG_DIR, "LATEST")


def percentile(values, q):
  if not values:
    return float("nan")
  xs = sorted(values)
  idx = (len(xs) - 1) * q
  lo = int(math.floor(idx))
  hi = int(math.ceil(idx))
  if lo == hi:
    return xs[lo]
  return xs[lo] + (xs[hi] - xs[lo]) * (idx - lo)


def pct(num, den):
  return 100.0 * num / den if den else 0.0


def resolve_path(path):
  if path:
    return path
  with open(LATEST) as f:
    return f.readline().strip()


def as_float(row, key):
  try:
    return float(row.get(key, 0.0) or 0.0)
  except (TypeError, ValueError):
    return 0.0


def as_int(row, key):
  try:
    return int(float(row.get(key, 0) or 0))
  except (TypeError, ValueError):
    return 0


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("path", nargs="?")
  parser.add_argument("--steer-max", type=float, default=2047.0,
                      help="host steering ceiling used for the drive (default: 2047)")
  parser.add_argument("--min-speed-kph", type=float, default=15.0,
                      help="ignore slower samples (default: 15)")
  args = parser.parse_args()

  path = resolve_path(args.path)
  with open(path, newline="") as f:
    rows = list(csv.DictReader(f))

  active = [
    r for r in rows
    if as_int(r, "lat_active")
    and as_int(r, "controls_active")
    and as_float(r, "v_ego_kph") >= args.min_speed_kph
    and not as_int(r, "steering_pressed")
  ]

  if not active:
    raise SystemExit("No active lateral-control samples matched the filters.")

  near95 = [r for r in active if abs(as_float(r, "steer_output_can")) >= args.steer_max * 0.95]
  near99 = [r for r in active if abs(as_float(r, "steer_output_can")) >= args.steer_max * 0.99]
  requested95 = [r for r in active if abs(as_float(r, "requested_steer")) >= 0.95]
  saturated = [r for r in active if as_int(r, "lat_saturated")]

  angle_errors = [abs(as_float(r, "angle_error_deg")) for r in active]
  sat_angle_errors = [abs(as_float(r, "angle_error_deg")) for r in saturated]
  requested_actual_gap = [
    abs(as_float(r, "requested_steer") - as_float(r, "output_steer"))
    for r in active
  ]

  max_can = max(abs(as_float(r, "steer_output_can")) for r in active)
  max_req = max(abs(as_float(r, "requested_steer")) for r in active)
  max_angle_error = max(angle_errors)

  print("Subaru steering log analysis")
  print("============================")
  print("file:                     %s" % path)
  print("active samples:           %d" % len(active))
  print("configured STEER_MAX:     %.0f" % args.steer_max)
  print("max |CAN steer|:          %.1f (%.1f%% of ceiling)" % (max_can, pct(max_can, args.steer_max)))
  print("max |requested steer|:    %.4f" % max_req)
  print("CAN >=95%% ceiling:       %.1f%%" % pct(len(near95), len(active)))
  print("CAN >=99%% ceiling:       %.1f%%" % pct(len(near99), len(active)))
  print("requested >=95%%:         %.1f%%" % pct(len(requested95), len(active)))
  print("PID saturated:            %.1f%%" % pct(len(saturated), len(active)))
  print("angle error mean:         %.2f deg" % mean(angle_errors))
  print("angle error p95:          %.2f deg" % percentile(angle_errors, 0.95))
  print("angle error max:          %.2f deg" % max_angle_error)
  if sat_angle_errors:
    print("angle error when sat avg: %.2f deg" % mean(sat_angle_errors))
    print("angle error when sat p95: %.2f deg" % percentile(sat_angle_errors, 0.95))
  print("req/output gap p95:       %.4f" % percentile(requested_actual_gap, 0.95))

  print("")
  if len(near95) / len(active) >= 0.05 and percentile(angle_errors, 0.95) >= 2.0:
    print("Interpretation: strong evidence of steering-authority saturation.")
    print("The controller frequently reached the configured ceiling while meaningful angle error remained.")
  elif len(requested95) / len(active) < 0.01 and percentile(angle_errors, 0.95) < 2.0:
    print("Interpretation: little evidence that the configured torque ceiling was the main bottleneck.")
    print("Planner/path calibration or a different lateral-control issue may be more important.")
  else:
    print("Interpretation: mixed result; inspect the corner segments before changing steering authority.")


if __name__ == "__main__":
  main()
