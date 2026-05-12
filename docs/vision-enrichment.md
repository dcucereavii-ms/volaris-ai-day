# Vision Enrichment

## Purpose

Augment tabular property features with **condition signals** extracted from internet imagery, lifting valuation accuracy especially for renovated/distressed properties that look identical in tabular form.

## Pipeline

```
property_hash + (address hint OR coords)
        │
        ▼
Image acquisition (licensed sources only)
  ├─ Listing portal API (with contract)
  ├─ Customer-uploaded photos
  ├─ Google Street View Static API
  ├─ Bing Maps / Mapillary
  └─ Sentinel-2 (roof, lot — open data)
        │
        ▼
Azure Blob: vision/raw/{property_hash}/{photo_hash}.jpg
        │
        ▼
Vision processing (AML batch job)
  ├─ Azure AI Vision: tags, OCR, object detection
  ├─ Azure OpenAI GPT-4o: rubric scoring (JSON-mode)
  └─ CLIP / Florence: 1024-d embedding
        │
        ▼
silver_property_vision (Delta)
  + Azure AI Search vector index (for visual comparables)
```

## Image source legal checklist

Per source, document:
- License type (open / commercial / per-request)
- Allowed uses (commercial, derivative, ML training)
- Attribution required
- Takedown contact
- Retention limit

**Never** scrape listing portals without explicit contract. Single fastest way to a lawsuit.

## Rubric

GPT-4o is asked to score each photo on:

| Dimension | Range | Notes |
|---|---|---|
| exterior_condition | 0.0–1.0 | Paint, siding, visible damage |
| roof_condition | 0.0–1.0 | Wear, missing tiles |
| curb_appeal | 0.0–1.0 | Landscaping, cleanliness |
| renovation_recency | 0.0–1.0 | Recently updated vs dated |
| visible_defects | list[string] | Cracks, water damage, etc. |
| confidence | 0.0–1.0 | Self-reported clarity |

JSON-mode response, `temperature=0`.

## Aggregation

Per `property_hash`:
- Median across photos with `confidence ≥ 0.5`.
- Drop properties with < 2 usable photos (use regional median fallback).
- Set `has_vision_score = 0` flag so model can degrade gracefully.

## Visual comparables (bonus uplift)

CLIP/Florence embeddings stored in **Azure AI Search vector index**.

At inference (or feature-engineering time):
1. Embed the subject property's photos.
2. ANN search for top-10 visually similar properties **in the same H3 region**.
3. Use their realized prices as features: `comp_median_price`, `comp_price_std`.

Often adds more uplift than the rubric scores alone — visual similarity captures style/era/quality cues that rubrics miss.

## Cost control

- **Cache** every score keyed by `(property_hash, photo_hash)` in Cosmos DB. Re-score only on photo refresh.
- Use **gpt-4o-mini** for first-pass triage, escalate ambiguous cases to gpt-4o.
- Batch process; never per-request inline (latency + cost).

## Quality audit

Monthly: random sample 1% of scored properties → human review. Track:
- Rubric score correlation with human assessment
- False renovation flags
- Confidence calibration

If correlation drops below 0.7 → freeze vision feature in model, investigate prompt drift.
