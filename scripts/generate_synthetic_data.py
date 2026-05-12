"""
Generate synthetic property valuation data for POC.

Produces a realistic-looking dataset already in 'anonymized' shape:
- property_hash, geo_h3_r8, postcode_prefix, sale_month, property_type,
  size_sqm, rooms, bathrooms, year_built, size_band, sale_price.

Usage:
    python scripts/generate_synthetic_data.py --rows 50000 --out data/synthetic
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

REGIONS = [
    # (postcode_prefix, h3_cell_seed, base_price_per_sqm, lat, lon)
    ("750", "881f1d4807fffff", 11000, 48.86, 2.34),   # Paris
    ("130", "881e3624a7fffff",  4500, 43.30, 5.40),   # Marseille
    ("690", "881f3a44d7fffff",  5500, 45.75, 4.85),   # Lyon
    ("330", "881e64b2c7fffff",  4800, 44.84, -0.58),  # Bordeaux
    ("440", "881f01122ffffff",  4200, 47.22, -1.55),  # Nantes
    ("310", "881e6024effffff",  3900, 43.60, 1.44),   # Toulouse
]

PROPERTY_TYPES = ["apartment", "house", "studio", "duplex"]
TYPE_PRICE_MULTIPLIER = {"apartment": 1.0, "house": 1.15, "studio": 0.85, "duplex": 1.25}


def size_band(sqm: float) -> str:
    if sqm < 40:  return "<40"
    if sqm < 100: return "40-100"
    if sqm < 200: return "100-200"
    return "200+"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=50000)
    ap.add_argument("--out", type=Path, default=Path("data/synthetic"))
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)
    out = args.out
    out.mkdir(parents=True, exist_ok=True)

    region_idx = rng.integers(0, len(REGIONS), size=args.rows)
    sizes = np.clip(rng.normal(75, 35, args.rows), 18, 350).round(0)
    rooms = np.clip((sizes / 22 + rng.normal(0, 0.7, args.rows)).round(0), 1, 8).astype(int)
    bathrooms = np.clip((rooms / 2.5 + rng.normal(0, 0.4, args.rows)).round(0), 1, 4).astype(int)
    year_built = rng.integers(1900, 2024, size=args.rows)
    age = 2026 - year_built

    ptype_idx = rng.integers(0, len(PROPERTY_TYPES), size=args.rows)
    ptype = np.array(PROPERTY_TYPES)[ptype_idx]
    type_mult = np.array([TYPE_PRICE_MULTIPLIER[p] for p in ptype])

    base_psm = np.array([REGIONS[i][2] for i in region_idx])
    postcode = np.array([REGIONS[i][0] for i in region_idx])
    h3_cell  = np.array([REGIONS[i][1] for i in region_idx])

    # Sale months over last 5 years
    months = pd.date_range("2021-01", "2026-04", freq="MS").strftime("%Y-%m")
    sale_month = months[rng.integers(0, len(months), size=args.rows)]

    # Macro effect: prices rose ~6% per year in this synthetic world
    year_offset = pd.to_datetime(sale_month + "-01").year - 2021
    macro_mult = (1.06 ** year_offset).values

    # Age penalty
    age_mult = np.clip(1.0 - age * 0.002, 0.5, 1.0)

    # Noise
    noise = rng.normal(1.0, 0.18, args.rows)

    price = base_psm * sizes * type_mult * macro_mult * age_mult * noise
    price = np.clip(price, 25_000, 5_000_000).round(-2)

    df = pd.DataFrame({
        "property_hash": [hashlib.sha256(f"poc-{i}".encode()).hexdigest()[:16]
                          for i in range(args.rows)],
        "geo_h3_r8": h3_cell,
        "postcode_prefix": postcode,
        "sale_month": sale_month,
        "property_type": ptype,
        "size_sqm": sizes,
        "rooms": rooms,
        "bathrooms": bathrooms,
        "year_built": year_built,
        "size_band": [size_band(s) for s in sizes],
        "sale_price": price,
    })

    # Write partitioned parquet (matches the production layout)
    df.to_parquet(out, partition_cols=["sale_month"], compression="snappy", index=False)
    print(f"Wrote {len(df):,} synthetic rows to {out}")
    print(df.head())
    print(f"\nPrice stats:\n{df['sale_price'].describe()}")


if __name__ == "__main__":
    main()
