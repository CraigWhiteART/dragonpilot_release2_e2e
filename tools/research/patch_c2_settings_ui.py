#!/usr/bin/env python3
"""Add a staged Subaru steering authority selector to DragonPilot R2 settings UI.

Apply this to a full DragonPilot R2 source tree containing:
  selfdrive/ui/qt/offroad/settings_dp.cc
  selfdrive/ui/qt/offroad/settings_dp.h

The selector stores an integer stage in dp_subaru_steer_stage:
  0 -> 2047 (stock)
  1 -> 2150
  2 -> 2300
  3 -> 2450
  4 -> 2600
  5 -> 2800
  6 -> 3071

This script does not flash Panda firmware and does not install the UI binary.
"""

from pathlib import Path
import sys

STAGES = [2047, 2150, 2300, 2450, 2600, 2800, 3071]


def replace_once(path: Path, old: str, new: str) -> None:
  text = path.read_text()
  count = text.count(old)
  if count != 1:
    raise RuntimeError(f"{path}: expected one match, found {count}")
  path.write_text(text.replace(old, new, 1))


def patch_cc(root: Path) -> None:
  path = root / "selfdrive/ui/qt/offroad/settings_dp.cc"

  old = """void DPCtrlPanel::add_car_specific_toggles() {
  add_toyota_toggles();
  add_hkg_toggles();
  add_vag_toggles();
}
"""

  new = """void DPCtrlPanel::add_subaru_toggles() {
  auto section = new LabelControl(QString::fromUtf8("🐉 ") + tr("Subaru - Research") + QString::fromUtf8(" 🐉"), "");
  addItem(section);

  static const std::vector<int> steer_stages{2047, 2150, 2300, 2450, 2600, 2800, 3071};

  auto steer_stage = new ButtonControl(
    tr("Steering Authority"),
    tr("2047"),
    tr("Research setting for Craig's 2017-19 Impreza/Crosstrek EPS (7ac00a00).\n"
       "2047 is stock. Higher values increase the maximum steering command available to openpilot.\n"
       "Requires the matching research Panda firmware and a reboot.\n"
       "Test progressively; 2800 and 3071 are higher-risk research stages."),
    this
  );

  auto refresh_steer_stage = [=]() {
    int stage = 0;
    try {
      std::string raw = params.get("dp_subaru_steer_stage");
      if (!raw.empty()) stage = std::stoi(raw);
    } catch (...) {
      stage = 0;
    }
    stage = std::max(0, std::min(stage, (int)steer_stages.size() - 1));
    steer_stage->setText(QString::number(steer_stages[stage]));
  };

  connect(steer_stage, &ButtonControl::clicked, [=]() {
    int stage = 0;
    try {
      std::string raw = params.get("dp_subaru_steer_stage");
      if (!raw.empty()) stage = std::stoi(raw);
    } catch (...) {
      stage = 0;
    }

    stage = (stage + 1) % steer_stages.size();

    if (stage >= 5) {
      const QString warning = stage == 5
        ? tr("2800 is a high research steering-authority stage. Continue only after lower stages have been logged without faults or overshoot.")
        : tr("3071 is the historical alternate Panda ceiling and is NOT publicly validated for EPS firmware 7ac00a00. Continue only after lower stages have been validated.");

      if (!ConfirmationDialog::confirm(warning, tr("Use %1").arg(steer_stages[stage]), this)) {
        return;
      }
    }

    params.put("dp_subaru_steer_stage", std::to_string(stage));
    steer_stage->setText(QString::number(steer_stages[stage]));
  });

  refresh_steer_stage();
  addItem(steer_stage);
}

void DPCtrlPanel::add_car_specific_toggles() {
  add_subaru_toggles();
  add_toyota_toggles();
  add_hkg_toggles();
  add_vag_toggles();
}
"""

  replace_once(path, old, new)


def patch_h(root: Path) -> None:
  path = root / "selfdrive/ui/qt/offroad/settings_dp.h"
  old = """  void add_car_specific_toggles();
  void add_toyota_toggles();
"""
  new = """  void add_car_specific_toggles();
  void add_subaru_toggles();
  void add_toyota_toggles();
"""
  replace_once(path, old, new)


def validate(root: Path) -> None:
  cc = (root / "selfdrive/ui/qt/offroad/settings_dp.cc").read_text()
  hh = (root / "selfdrive/ui/qt/offroad/settings_dp.h").read_text()

  assert "void DPCtrlPanel::add_subaru_toggles()" in cc
  assert "dp_subaru_steer_stage" in cc
  for value in STAGES:
    assert str(value) in cc
  assert "add_subaru_toggles();" in cc
  assert "void add_subaru_toggles();" in hh
  assert "3071 is the historical alternate Panda ceiling" in cc


def main() -> None:
  if len(sys.argv) != 2:
    raise SystemExit(f"usage: {sys.argv[0]} /path/to/full-r2-source")

  root = Path(sys.argv[1]).resolve()
  if not (root / "selfdrive/ui/qt/offroad/settings_dp.cc").exists():
    raise SystemExit("full R2 settings_dp.cc not found")

  patch_cc(root)
  patch_h(root)
  validate(root)
  print("Patched DragonPilot R2 Subaru staged steering selector")
  print("Stages:", STAGES)


if __name__ == "__main__":
  main()
