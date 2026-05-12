# Design

## Problem statement

Legacy hedonic property valuation model trained in 2009. 17 years of regime change (2008 recovery, ZIRP, COVID, rate hikes) have eroded calibration. Sensitive bank/insurance training data cannot leave on-prem in raw form.

## Goals

1. Retrain on a privacy-preserving anonymized subset.
2. Enrich with public data (registry, census, OSM, macro indicators).
3. Add vision-derived condition features from public/licensed imagery.
4. Production endpoint with versioning, A/B testing, monitoring, rollback.
5. Monthly automated retraining with promotion gates.

## Non-goals (MVP)

- Federated/confidential-compute training (deferred to v2 if regulator demands).
- Real-time vision scoring at request time (start with cached scores; add live later).
- Multi-region active-active deployment.

## Feature catalog

| Group | Feature | Source | Notes |
|---|---|---|---|
| Property | size_sqm, rooms, bathrooms, year_built, property_type | On-prem (anonymized) | Direct |
| Property | log_size_sqm, age_years | Derived | In gold layer |
| Geo | geo_h3_r8, postcode_prefix | On-prem (generalized) | k-anonymity preserved |
| Geo | dist_school, dist_transit, amenity_count_1km | OpenStreetMap | Pre-aggregated per H3 cell |
| Socio | median_income, unemployment_rate, pop_density | Census / Eurostat | Per postcode prefix |
| Macro | mortgage_rate, cpi, regional_gdp_growth | Central bank APIs | Per sale_month |
| Risk | flood_zone, seismic_zone | Public hazard layers | Per H3 cell |
| Vision | condition_score, roof_condition, curb_appeal, renovation_flag | AOAI GPT-4o | Per property_hash, median across photos |
| Vision | visual_embedding (1024-d) | CLIP / Florence | For comparable retrieval |
| Comparables | recent_sales_h3, price_per_sqm_h3 | Derived from anonymized sales | Time-windowed, leakage-safe |
| Target | sale_price | On-prem | Log-transform recommended |

## Model design

### Baseline (AutoML)
- Task: regression
- Primary metric: `normalized_root_mean_squared_error`
- Featurization: custom (categoricals declared)
- Time-aware holdout: most recent 6 months
- Output: AutoML leaderboard top-3 ensembled

### Champion candidate (LightGBM)
- Objective: `regression_l1` (MAE — robust to outlier sales)
- Target transform: `log1p(sale_price)`, inverse at inference
- Categorical encoding: native LightGBM categoricals on `geo_h3_r8`, `postcode_prefix`, `property_type`
- Cross-validation: rolling-origin (5 folds, expanding window)
- Calibration: post-hoc isotonic on residuals per region
- Uncertainty: quantile regression (q10, q50, q90) → returns price + low/high band

### Vision features
- Aggregate per property (median across photos).
- Confidence-weighted: drop scores where GPT-4o reports `confidence < 0.5`.
- Missing handling: impute with regional median + `has_vision_score` flag.

## Inference contract

```json
// Request
{
  "property_hash": "a1b2c3d4...",
  "size_sqm": 95,
  "rooms": 3,
  "bathrooms": 1,
  "year_built": 1968,
  "property_type": "apartment",
  "geo_h3_r8": "881f1d4807fffff",
  "postcode_prefix": "75011",
  "photo_urls": ["https://..."]   // optional
}
```

```json
// Response
{
  "model_version": "2.3.1",
  "price": 412500,
  "price_low_q10": 378000,
  "price_high_q90": 451000,
  "currency": "EUR",
  "condition_score": 0.72,
  "top_drivers": [
    { "feature": "geo_h3_r8", "contribution": 145000 },
    { "feature": "size_sqm",  "contribution": 98000 },
    { "feature": "condition_score", "contribution": 22000 }
  ],
  "served_by": "blue",
  "request_id": "..."
}
```

## Evaluation slices

Always report metrics globally **and** per:
- Region (postcode prefix bucket)
- Property type
- Price decile
- Vintage decade
- Vision-available vs vision-missing

Promotion gate: no slice may regress > 5% MAPE vs champion.
