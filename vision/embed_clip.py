"""
Generate 1024-d image embeddings using Azure AI Vision (multimodal).

Embeddings are written to Parquet and can be loaded into Azure AI Search
as a vector index for visual comparable retrieval.
"""
from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

import pandas as pd
import requests
from azure.identity import DefaultAzureCredential

LOG = logging.getLogger("embed")
logging.basicConfig(level=logging.INFO)

API_VERSION = "2024-02-01"
MODEL_VERSION = "2023-04-15"


def get_token() -> str:
    cred = DefaultAzureCredential()
    return cred.get_token("https://cognitiveservices.azure.com/.default").token


def embed_url(endpoint: str, token: str, image_url: str) -> list[float] | None:
    url = (f"{endpoint}/computervision/retrieval:vectorizeImage"
           f"?api-version={API_VERSION}&model-version={MODEL_VERSION}")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        r = requests.post(url, headers=headers, json={"url": image_url}, timeout=30)
        r.raise_for_status()
        return r.json()["vector"]
    except Exception as exc:
        LOG.warning("Embed failed: %s", exc)
        return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--endpoint", default=os.environ.get("AI_VISION_ENDPOINT"))
    args = ap.parse_args()
    assert args.endpoint, "Set AI_VISION_ENDPOINT or pass --endpoint"

    manifest = (pd.read_parquet(args.manifest)
                if args.manifest.suffix != ".csv"
                else pd.read_csv(args.manifest))
    token = get_token()

    rows = []
    for _, r in manifest.iterrows():
        vec = embed_url(args.endpoint, token, r["photo_url"])
        if vec:
            rows.append({
                "property_hash": r["property_hash"],
                "photo_hash":    r["photo_hash"],
                "embedding":     vec,
            })

    df = pd.DataFrame(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(args.output, index=False)
    LOG.info("Wrote %d embeddings to %s", len(df), args.output)


if __name__ == "__main__":
    main()
