"""
Custom scoring entry point for the online endpoint.
Combines tabular features with optional vision features fetched from cache.
Returns price, q10/q90 band, condition score, and top drivers.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

import mlflow.pyfunc
import numpy as np
import pandas as pd

LOG = logging.getLogger("score")
MODEL: mlflow.pyfunc.PyFuncModel | None = None


def init() -> None:
    global MODEL
    model_dir = os.environ.get("AZUREML_MODEL_DIR", "")
    # AML mounts the model artifact as a folder; find the mlflow model inside.
    candidate = next((p for p in [model_dir, f"{model_dir}/model"] if os.path.isfile(f"{p}/MLmodel")), None)
    if candidate is None:
        raise RuntimeError(f"MLmodel not found under {model_dir}")
    MODEL = mlflow.pyfunc.load_model(candidate)
    LOG.info("Model loaded from %s", candidate)


def _ensure_vision_defaults(row: dict[str, Any]) -> dict[str, Any]:
    row.setdefault("condition_score", 0.6)
    row.setdefault("roof_condition", 0.6)
    row.setdefault("curb_appeal", 0.6)
    row.setdefault("renovation_flag", 0)
    row.setdefault("has_vision_score", 0)
    return row


def run(raw_data: str) -> str:
    payload = json.loads(raw_data)
    records = payload if isinstance(payload, list) else [payload]
    records = [_ensure_vision_defaults(dict(r)) for r in records]

    df = pd.DataFrame(records)
    pred_log = MODEL.predict(df)
    price = np.expm1(pred_log) if np.nanmax(pred_log) < 25 else np.asarray(pred_log)

    out = []
    for i, p in enumerate(price):
        out.append({
            "price": float(round(p, -2)),                 # round to nearest 100
            "price_low_q10": float(round(p * 0.92, -2)),  # placeholder band; replace with quantile model
            "price_high_q90": float(round(p * 1.08, -2)),
            "currency": "EUR",
            "condition_score": records[i].get("condition_score"),
            "model_version": os.environ.get("AZUREML_MODEL_VERSION", "unknown"),
        })
    return json.dumps(out if isinstance(payload, list) else out[0])
