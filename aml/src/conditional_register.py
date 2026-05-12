"""
Promote challenger to registry only if all gates pass.

Gates:
  - Global MAPE improves by >= 2% relative.
  - No region or property-type slice regresses by > 5% relative.
  - Calibration ratio in [0.97, 1.03].
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import mlflow

GLOBAL_IMPROVE = 0.02
SLICE_REGRESSION_MAX = 0.05
CALIB_LOW, CALIB_HIGH = 0.97, 1.03


def slice_regression(champ: dict, chal: dict, key: str) -> tuple[bool, list[str]]:
    failures = []
    for k, champ_v in champ.get(key, {}).items():
        chal_v = chal.get(key, {}).get(k)
        if chal_v is None:
            continue
        rel = (chal_v - champ_v) / max(champ_v, 1e-9)
        if rel > SLICE_REGRESSION_MAX:
            failures.append(f"{key}={k}: champion {champ_v:.4f} vs challenger {chal_v:.4f} ({rel:+.1%})")
    return (len(failures) == 0), failures


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True, type=Path)
    ap.add_argument("--model", required=True, type=Path)
    ap.add_argument("--register-name", required=True)
    args = ap.parse_args()

    report = json.loads((args.report / "report.json").read_text())
    champ = report["champion"]
    chal = report["challenger"]

    failures: list[str] = []

    rel_improve = (champ["mape_global"] - chal["mape_global"]) / max(champ["mape_global"], 1e-9)
    print(f"Global MAPE: champion {champ['mape_global']:.4f}  challenger {chal['mape_global']:.4f}  ({rel_improve:+.1%})")
    if rel_improve < GLOBAL_IMPROVE:
        failures.append(f"Global improvement {rel_improve:.1%} < required {GLOBAL_IMPROVE:.0%}")

    for key in ("by_property_type", "by_postcode_prefix"):
        ok, fails = slice_regression(champ, chal, key)
        if not ok:
            failures.extend(fails)

    calib = chal["calibration_ratio"]
    print(f"Calibration ratio (challenger): {calib:.4f}")
    if not (CALIB_LOW <= calib <= CALIB_HIGH):
        failures.append(f"Calibration ratio {calib:.4f} outside [{CALIB_LOW}, {CALIB_HIGH}]")

    if failures:
        print("PROMOTION GATES FAILED:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(0)  # do not fail pipeline; just skip registration

    print("All gates passed. Registering model...")
    mlflow.register_model(
        model_uri=f"file://{args.model.resolve()}",
        name=args.register_name,
        tags={
            "promoted_by": "automated_gates",
            "challenger_mape": str(chal["mape_global"]),
            "champion_mape": str(champ["mape_global"]),
        },
    )
    print(f"Registered as {args.register_name}")


if __name__ == "__main__":
    main()
