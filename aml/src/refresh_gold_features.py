"""
Refresh the gold_features data asset for a given snapshot date.
In production this would invoke the Fabric pipeline + register a new AML data asset.
This stub is a placeholder for the retrain pipeline.
"""
from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--source",
                    default=os.environ.get("GOLD_SOURCE", "/mnt/onelake/gold_features"))
    ap.add_argument("--output", default="./outputs/gold")
    args = ap.parse_args()

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    src = Path(args.source)
    if not src.exists():
        # In production, trigger the Fabric pipeline here via REST and wait for completion.
        # For local/dev runs, allow a pre-staged copy.
        raise SystemExit(f"Gold source {src} not found. Trigger Fabric pipeline first.")

    print(f"Copying {src} -> {out} for snapshot {args.snapshot}")
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(src, out)
    print("Done.")


if __name__ == "__main__":
    main()
