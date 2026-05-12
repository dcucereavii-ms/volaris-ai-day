"""
On-prem anonymization for property valuation data.

Reads the raw extract, drops direct identifiers, generalizes quasi-identifiers,
applies k-anonymity, and writes partitioned Parquet ready for upload.

Usage:
    python anonymize.py --input staging/raw_extract.parquet --output staging/upload/

Requires env var ANON_SALT (32+ hex chars). Salt MUST stay on-prem.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

import h3
import numpy as np
import pandas as pd

K_THRESHOLD = 10
QUASI_IDS = ["geo_h3_r8", "property_type", "sale_month", "size_band"]
DROP_COLUMNS = [
    "owner_name", "owner_id", "account_number",
    "street_address", "phone", "email",
]


def get_salt() -> str:
    salt = os.environ.get("ANON_SALT")
    if not salt or len(salt) < 32:
        sys.exit("ERROR: env var ANON_SALT must be set (>=32 hex chars).")
    return salt


def hash_id(value: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}{value}".encode()).hexdigest()[:16]


def generalize(df: pd.DataFrame, salt: str) -> pd.DataFrame:
    df = df.drop(columns=DROP_COLUMNS, errors="ignore")

    df["property_hash"] = df["property_id"].astype(str).map(lambda v: hash_id(v, salt))
    df = df.drop(columns=["property_id"])

    df["geo_h3_r8"] = df.apply(
        lambda r: h3.geo_to_h3(float(r["latitude"]), float(r["longitude"]), 8),
        axis=1,
    )
    df = df.drop(columns=["latitude", "longitude"])

    df["postcode_prefix"] = df["postcode"].astype(str).str[:3]
    df = df.drop(columns=["postcode"])

    df["sale_month"] = pd.to_datetime(df["sale_date"]).dt.to_period("M").astype(str)
    df = df.drop(columns=["sale_date"])

    return df


def k_anonymity_filter(df: pd.DataFrame, quasi_ids: list[str], k: int) -> pd.DataFrame:
    counts = df.groupby(quasi_ids).size().rename("group_size").reset_index()
    merged = df.merge(counts, on=quasi_ids, how="left")
    safe = merged[merged["group_size"] >= k].drop(columns=["group_size"])
    dropped = len(df) - len(safe)
    pct = dropped / max(len(df), 1)
    print(f"k-anonymity (k={k}): kept {len(safe):,} / {len(df):,} rows, dropped {dropped:,} ({pct:.1%})")
    print(f"k-anon group-size distribution:\n{counts['group_size'].describe()}")
    return safe


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--k", type=int, default=K_THRESHOLD)
    args = parser.parse_args()

    salt = get_salt()
    print(f"Reading {args.input}...")
    raw = pd.read_parquet(args.input)
    print(f"Source rows: {len(raw):,}")

    print("Generalizing...")
    anon = generalize(raw, salt)

    print("Applying k-anonymity...")
    safe = k_anonymity_filter(anon, QUASI_IDS, args.k)

    args.output.mkdir(parents=True, exist_ok=True)
    print(f"Writing partitioned parquet to {args.output}...")
    safe.to_parquet(
        args.output,
        partition_cols=["sale_month"],
        compression="snappy",
        index=False,
    )
    print("Done. Review k-anon stats above and obtain DPO sign-off before upload.")


if __name__ == "__main__":
    main()
