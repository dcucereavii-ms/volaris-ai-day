"""
Train a LightGBM regressor on the gold_features data asset.
Logs to MLflow, performs time-aware split, registers the model artifact.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import lightgbm as lgb
import mlflow
import mlflow.lightgbm
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_percentage_error, r2_score

CATEGORICAL = ["geo_h3_r8", "postcode_prefix", "property_type", "size_band"]
DROP = ["property_hash", "ingested_at", "source_file"]


def load(data_path: Path) -> pd.DataFrame:
    files = list(data_path.rglob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"No parquet files under {data_path}")
    return pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)


def prepare(df: pd.DataFrame, target: str) -> tuple[pd.DataFrame, pd.Series]:
    df = df.drop(columns=[c for c in DROP if c in df.columns], errors="ignore")
    for c in CATEGORICAL:
        if c in df.columns:
            df[c] = df[c].astype("category")
    y = df[target]
    X = df.drop(columns=[target])
    return X, y


def time_split(X: pd.DataFrame, y: pd.Series, holdout_months: int = 6):
    months = sorted(X["sale_month"].astype(str).unique())
    cutoff = months[-holdout_months]
    train_mask = X["sale_month"].astype(str) < cutoff
    return X[train_mask], X[~train_mask], y[train_mask], y[~train_mask]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, type=Path)
    ap.add_argument("--target", default="sale_price")
    ap.add_argument("--output", type=Path, default=Path("./outputs/model"))
    ap.add_argument("--register-name", default=None)
    args = ap.parse_args()

    mlflow.lightgbm.autolog()

    print("Loading data...")
    df = load(args.data)
    print(f"Rows: {len(df):,}")

    X, y = prepare(df, args.target)
    X_tr, X_te, y_tr, y_te = time_split(X, y, holdout_months=6)
    print(f"Train: {len(X_tr):,} | Test: {len(X_te):,}")

    # Log-transform target — robust for skewed prices
    y_tr_log = np.log1p(y_tr)
    y_te_log = np.log1p(y_te)

    model = lgb.LGBMRegressor(
        n_estimators=2000,
        learning_rate=0.03,
        num_leaves=127,
        min_data_in_leaf=50,
        feature_fraction=0.8,
        bagging_fraction=0.8,
        bagging_freq=5,
        objective="regression_l1",
        random_state=42,
    )
    model.fit(
        X_tr, y_tr_log,
        eval_set=[(X_te, y_te_log)],
        eval_metric="l1",
        categorical_feature=[c for c in CATEGORICAL if c in X_tr.columns],
        callbacks=[lgb.early_stopping(50), lgb.log_evaluation(100)],
    )

    pred = np.expm1(model.predict(X_te))
    mape = mean_absolute_percentage_error(y_te, pred)
    r2 = r2_score(y_te, pred)
    mlflow.log_metric("mape", mape)
    mlflow.log_metric("r2", r2)
    print(f"Holdout MAPE: {mape:.4f} | R2: {r2:.4f}")

    # Slice metrics
    slice_df = X_te.copy()
    slice_df["actual"] = y_te.values
    slice_df["pred"] = pred
    for col in ["property_type", "postcode_prefix"]:
        if col in slice_df.columns:
            grp = slice_df.groupby(col, observed=True).apply(
                lambda g: mean_absolute_percentage_error(g["actual"], g["pred"])
            )
            for k, v in grp.items():
                mlflow.log_metric(f"mape_{col}_{k}", float(v))

    args.output.mkdir(parents=True, exist_ok=True)
    mlflow.lightgbm.save_model(model, str(args.output))

    if args.register_name:
        mlflow.lightgbm.log_model(
            model, artifact_path="model",
            registered_model_name=args.register_name,
        )

    print(f"Model saved to {args.output}")


if __name__ == "__main__":
    main()
