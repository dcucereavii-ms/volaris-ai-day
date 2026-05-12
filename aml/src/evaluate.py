"""
Score challenger and champion on a fixed holdout, write a comparison report.
The conditional_register step reads this report to enforce promotion gates.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import mlflow
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_percentage_error


def load_holdout(path: Path) -> pd.DataFrame:
    files = list(path.rglob("*.parquet"))
    return pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)


def predict(model_uri: str, X: pd.DataFrame) -> np.ndarray:
    model = mlflow.pyfunc.load_model(model_uri)
    pred = model.predict(X)
    # Models trained on log target — invert. Heuristic: if max < 25, assume log space.
    return np.expm1(pred) if np.nanmax(pred) < 25 else np.asarray(pred)


def slice_mape(df: pd.DataFrame, col: str) -> dict[str, float]:
    out = {}
    for k, g in df.groupby(col, observed=True):
        if len(g) >= 30:
            out[str(k)] = float(mean_absolute_percentage_error(g["y"], g["pred"]))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--challenger", required=True, type=Path)
    ap.add_argument("--champion-uri", required=True)
    ap.add_argument("--holdout", required=True, type=Path)
    ap.add_argument("--report", required=True, type=Path)
    args = ap.parse_args()

    df = load_holdout(args.holdout)
    y = df["sale_price"].values
    X = df.drop(columns=["sale_price"])

    print("Scoring champion...")
    champ_pred = predict(args.champion_uri, X)
    print("Scoring challenger...")
    chal_pred = predict(str(args.challenger), X)

    def metrics(pred: np.ndarray) -> dict:
        scored = X.copy()
        scored["y"] = y
        scored["pred"] = pred
        return {
            "mape_global": float(mean_absolute_percentage_error(y, pred)),
            "by_property_type": slice_mape(scored, "property_type"),
            "by_postcode_prefix": slice_mape(scored, "postcode_prefix"),
            "calibration_ratio": float(np.mean(pred) / np.mean(y)),
        }

    report = {
        "champion": metrics(champ_pred),
        "challenger": metrics(chal_pred),
    }

    args.report.mkdir(parents=True, exist_ok=True)
    out_file = args.report / "report.json"
    out_file.write_text(json.dumps(report, indent=2))
    print(f"Wrote {out_file}")
    print(json.dumps(
        {"champion_mape": report["champion"]["mape_global"],
         "challenger_mape": report["challenger"]["mape_global"]},
        indent=2,
    ))


if __name__ == "__main__":
    main()
