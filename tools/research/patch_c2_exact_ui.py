#!/usr/bin/env python3
"""Patch the exact DragonPilot 2023 C2 UI binaries with Subaru steering stages.

The release2_e2e repository ships prebuilt, non-stripped Android/EON UI binaries
rather than their matching settings source. The exact binaries were inspected via
DWARF/disassembly. This patch repurposes the Toyota cruise-override widget on this
Subaru-only research branch into an explicit enable toggle plus a 0..6 stage
spinbox. Everything else in the UI binary is left unchanged.

Stage mapping:
  0=2047, 1=2150, 2=2300, 3=2450, 4=2600, 5=2800, 6=3071
"""

from pathlib import Path
import hashlib
import sys


ORIGINALS = {
  "_ui": {
    "sha256": "c3240fa84b23aff8b141ad3265c99eb803e59fe9539e558bbb872b4a1affb00a",
    "patched_sha256": "8b92ddbf63830a21f6a71ec52aad5f5949287e438676738a90053a54896c10cc",
    "widget": 0x77000,
  },
  "_ui_nonav": {
    "sha256": "bac87b8a1572512ce2ac8b0663ddab6ed538c59d630d2e02b596628db2d38422",
    "patched_sha256": "3dd2e552b5609c1b860bc93e4ba4e04c3d08af81043ebbc881d3924365caa14b",
    "widget": 0x6FA10,
  },
}


def replace_cstr(data, old, new):
  old = old.encode()
  new = new.encode()
  if len(new) > len(old):
    raise RuntimeError(f"replacement too long: {new!r} > {old!r}")

  hits = []
  start = 0
  while True:
    pos = data.find(old, start)
    if pos < 0:
      break
    hits.append(pos)
    start = pos + 1

  if len(hits) != 1:
    raise RuntimeError(f"expected one {old!r}, found {len(hits)}")

  pos = hits[0]
  data[pos:pos + len(old)] = new + (b"\0" * (len(old) - len(new)))
  return pos


def patch_instruction(data, offset, old_hex, new_hex):
  old = bytes.fromhex(old_hex)
  new = bytes.fromhex(new_hex)
  actual = bytes(data[offset:offset + 4])
  if actual != old:
    raise RuntimeError(
      f"instruction mismatch at {offset:#x}: got {actual.hex()}, expected {old.hex()}"
    )
  data[offset:offset + 4] = new


def patch(path):
  key = path.name
  if key not in ORIGINALS:
    raise RuntimeError(f"unsupported UI binary: {path}")

  meta = ORIGINALS[key]
  data = bytearray(path.read_bytes())
  before = hashlib.sha256(data).hexdigest()

  if before == meta["patched_sha256"]:
    print(f"{key}: already patched")
    return

  if before != meta["sha256"]:
    raise RuntimeError(f"{key}: unexpected original SHA256 {before}")

  stage_offset = replace_cstr(
    data, "dp_toyota_cruise_override_speed", "dp_subaru_steer_stage"
  )
  replace_cstr(data, "Override Speed When Below", "Steering Authority Stage")
  replace_cstr(
    data,
    "Override feature will be enabled when set cruise speed is lower than this value.",
    "0=2047  1=2150  2=2300  3=2450  4=2600  5=2800  6=3071. Reboot required.",
  )

  # This unit string is specific to the spinbox above in both exact binaries.
  unit_offset = stage_offset + 0x9E
  if bytes(data[unit_offset:unit_offset + 5]) != b" km/h":
    raise RuntimeError(f"{key}: stage unit string moved")
  data[unit_offset:unit_offset + 5] = b" / 6\0"

  replace_cstr(data, "dp_toyota_cruise_override", "dp_subaru_steer_enable")
  replace_cstr(data, "Turn On Cruise Speed Override", "Enable Subaru Steering Stages")
  replace_cstr(
    data,
    "This feature will let you set your cruise speed below vehicle standard. (usually at 26~40 km/h)",
    "Subaru EPS 7ac00a00 research. Stage 0 is stock. Increase progressively; reboot after changes.",
  )

  # The repurposed widget remains adjacent to Toyota controls in the original
  # DPCarPanel, so label the shared section accurately on this research branch.
  replace_cstr(data, "Toyota / Lexus", "Subaru/Toyota")

  fn = meta["widget"]

  # QString::fromAscii_helper explicit length: 31 -> 21
  patch_instruction(data, fn + 0x68, "e1130032", "a1028052")

  # ParamSpinBoxControl min/max: 5..60 -> 0..6. Step stays 1.
  patch_instruction(data, fn + 0x108, "a5008052", "05008052")
  patch_instruction(data, fn + 0x124, "e60f1e32", "c6008052")

  # Paired toggle parameter QString length: 25 -> 22.
  patch_instruction(data, fn + 0x2D8, "21038052", "c1028052")

  path.write_bytes(data)

  after = hashlib.sha256(data).hexdigest()
  if after != meta["patched_sha256"]:
    raise RuntimeError(f"{key}: patched SHA256 mismatch {after}")

  print(f"{key}: patched {before[:12]} -> {after[:12]}")


def main():
  if len(sys.argv) < 2:
    raise SystemExit(f"usage: {sys.argv[0]} /path/to/_ui [/path/to/_ui_nonav]")

  for arg in sys.argv[1:]:
    patch(Path(arg))


if __name__ == "__main__":
  main()
