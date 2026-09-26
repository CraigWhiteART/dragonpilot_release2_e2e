#!/usr/bin/env python3
"""Patch the exact DragonPilot 2023 C2 UI binaries with Subaru steering stages.

The release ships prebuilt Android/EON UI binaries and a prebuilt Params
extension. To remain compatible with that exact C2 runtime, this patch keeps the
already-registered Toyota parameter keys and only repurposes their UI labels and
range on this Subaru research branch:

  dp_toyota_cruise_override       -> research enable toggle
  dp_toyota_cruise_override_speed -> research stage 0..6

Stage mapping:
  0=2047, 1=2150, 2=2300, 3=2450, 4=2600, 5=2800, 6=3071

The patch accepts either the untouched release binaries or the earlier
first-generation research binaries that used unregistered dp_subaru_* key names;
those are migrated back to the registered C2 keys deterministically.
"""

from pathlib import Path
import hashlib
import sys


ORIGINALS = {
  "_ui": {
    "sha256": "c3240fa84b23aff8b141ad3265c99eb803e59fe9539e558bbb872b4a1affb00a",
    "legacy_patched_sha256": "8b92ddbf63830a21f6a71ec52aad5f5949287e438676738a90053a54896c10cc",
    "patched_sha256": "df17a7d160ae3d2df527892345d43475f5846d4f532ffc79874059035cf15a2c",
    "widget": 0x77000,
  },
  "_ui_nonav": {
    "sha256": "bac87b8a1572512ce2ac8b0663ddab6ed538c59d630d2e02b596628db2d38422",
    "legacy_patched_sha256": "3dd2e552b5609c1b860bc93e4ba4e04c3d08af81043ebbc881d3924365caa14b",
    "patched_sha256": "5eb06f3e6d45c8743332e7dadd0cf7abacbe5397184c363db3b7d4e8626c7ad2",
    "widget": 0x6FA10,
  },
}


def replace_cstr(data, old, new):
  old_b = old.encode()
  new_b = new.encode()
  if len(new_b) > len(old_b):
    raise RuntimeError(f"replacement too long: {new_b!r} > {old_b!r}")

  hits = []
  start = 0
  while True:
    pos = data.find(old_b, start)
    if pos < 0:
      break
    hits.append(pos)
    start = pos + 1

  if len(hits) != 1:
    raise RuntimeError(f"expected one {old_b!r}, found {len(hits)}")

  pos = hits[0]
  data[pos:pos + len(old_b)] = new_b + (b"\0" * (len(old_b) - len(new_b)))
  return pos


def restore_padded_cstr(data, old, new):
  """Restore a longer string into the zero-padded slot used by the legacy patch."""
  old_b = old.encode()
  new_b = new.encode()
  pos = data.find(old_b)
  if pos < 0:
    raise RuntimeError(f"legacy string missing: {old_b!r}")

  padding = data[pos + len(old_b):pos + len(new_b)]
  if any(padding):
    raise RuntimeError(f"legacy string slot is not zero padded: {old_b!r}")

  data[pos:pos + len(new_b)] = new_b
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


def identify(before):
  for key, meta in ORIGINALS.items():
    if before in (
      meta["sha256"],
      meta["legacy_patched_sha256"],
      meta["patched_sha256"],
    ):
      return key, meta
  return None, None


def migrate_legacy_patch(data, key, meta):
  # Restore registered Param names and their original QString explicit lengths.
  restore_padded_cstr(
    data, "dp_subaru_steer_stage", "dp_toyota_cruise_override_speed"
  )
  restore_padded_cstr(
    data, "dp_subaru_steer_enable", "dp_toyota_cruise_override"
  )

  fn = meta["widget"]
  patch_instruction(data, fn + 0x68, "a1028052", "e1130032")
  patch_instruction(data, fn + 0x2D8, "c1028052", "21038052")

  after = hashlib.sha256(data).hexdigest()
  if after != meta["patched_sha256"]:
    raise RuntimeError(f"{key}: migrated SHA256 mismatch {after}")


def patch_original(data, key, meta):
  # Keep the original registered Param names. params_pyx.so rejects unknown keys.
  stage_offset = data.find(b"dp_toyota_cruise_override_speed")
  if stage_offset < 0:
    raise RuntimeError(f"{key}: Toyota stage Param string missing")

  replace_cstr(data, "Override Speed When Below", "Steering Authority Stage")
  replace_cstr(
    data,
    "Override feature will be enabled when set cruise speed is lower than this value.",
    "0=2047  1=2150  2=2300  3=2450  4=2600  5=2800  6=3071. Reboot required.",
  )

  unit_offset = stage_offset + 0x9E
  if bytes(data[unit_offset:unit_offset + 5]) != b" km/h":
    raise RuntimeError(f"{key}: stage unit string moved")
  data[unit_offset:unit_offset + 5] = b" / 6\0"

  replace_cstr(data, "Turn On Cruise Speed Override", "Enable Subaru Steering Stages")
  replace_cstr(
    data,
    "This feature will let you set your cruise speed below vehicle standard. (usually at 26~40 km/h)",
    "Subaru EPS 7ac00a00 research. Stage 0 is stock. Increase progressively; reboot after changes.",
  )
  replace_cstr(data, "Toyota / Lexus", "Subaru/Toyota")

  fn = meta["widget"]
  # ParamSpinBoxControl min/max: 5..60 -> 0..6. Step remains 1.
  patch_instruction(data, fn + 0x108, "a5008052", "05008052")
  patch_instruction(data, fn + 0x124, "e60f1e32", "c6008052")

  after = hashlib.sha256(data).hexdigest()
  if after != meta["patched_sha256"]:
    raise RuntimeError(f"{key}: patched SHA256 mismatch {after}")


def validate(data, key, meta):
  digest = hashlib.sha256(data).hexdigest()
  if digest != meta["patched_sha256"]:
    raise RuntimeError(f"{key}: final SHA256 mismatch {digest}")

  for marker in (
    b"dp_toyota_cruise_override",
    b"dp_toyota_cruise_override_speed",
    b"Enable Subaru Steering Stages",
    b"Steering Authority Stage",
  ):
    if marker not in data:
      raise RuntimeError(f"{key}: marker missing {marker!r}")

  for forbidden in (b"dp_subaru_steer_enable", b"dp_subaru_steer_stage"):
    if forbidden in data:
      raise RuntimeError(f"{key}: incompatible Param marker remains {forbidden!r}")


def patch(path):
  data = bytearray(path.read_bytes())
  before = hashlib.sha256(data).hexdigest()
  key, meta = identify(before)

  if key is None:
    raise RuntimeError(f"{path}: unsupported UI SHA256 {before}")

  if before == meta["patched_sha256"]:
    validate(data, key, meta)
    print(f"{path}: already compatible as {key}")
    return

  if before == meta["legacy_patched_sha256"]:
    migrate_legacy_patch(data, key, meta)
  else:
    patch_original(data, key, meta)

  validate(data, key, meta)
  path.write_bytes(data)
  after = hashlib.sha256(data).hexdigest()
  print(f"{path}: patched as {key} {before[:12]} -> {after[:12]}")


def main():
  if len(sys.argv) < 2:
    raise SystemExit(f"usage: {sys.argv[0]} /path/to/_ui [/path/to/_ui_nonav]")

  for arg in sys.argv[1:]:
    patch(Path(arg))


if __name__ == "__main__":
  main()
