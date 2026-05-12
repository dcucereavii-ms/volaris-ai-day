# Data Flow

## Bronze → Silver → Gold

### Bronze (`bronze_valuations`)
1:1 with anonymized parquet from on-prem. No transformations.

| Column | Type | Notes |
|---|---|---|
| property_hash | string | Salted SHA-256, on-prem salt |
| geo_h3_r8 | string | H3 cell at resolution 8 (~0.7 km²) |
| postcode_prefix | string | First 3 chars |
| sale_month | string | YYYY-MM |
| property_type | string | apartment / house / commercial |
| size_sqm | double | |
| rooms | int | |
| bathrooms | int | |
| year_built | int | |
| size_band | string | k-anon bucket |
| sale_price | double | Target |

### Silver (`silver_valuations_enriched`)
Bronze + public data joins.

Joins:
- `osm_h3_features` on `geo_h3_r8` → amenity counts, distances
- `census_postcode` on `postcode_prefix` → income, density
- `macro_indicators` on `sale_month` → rates, CPI
- `hazard_layers` on `geo_h3_r8` → flood/seismic flags

### Vision (`silver_property_vision`)
Per-property aggregates from vision pipeline.

| Column | Type |
|---|---|
| property_hash | string |
| condition_score | double (0–1) |
| roof_condition | double (0–1) |
| curb_appeal | double (0–1) |
| renovation_flag | int (0/1) |
| photo_count | int |
| visual_embedding | array<float> (1024) |
| last_scored_at | timestamp |

### Gold (`gold_features`)
Silver + vision + derived features. Final ML input.

Partitioning: `sale_month` (string).
Format: Delta.
Optimization: `OPTIMIZE` + `ZORDER BY (geo_h3_r8, property_type)` weekly.

## Lineage

```
on-prem.staging/raw_extract.parquet
  │ (anonymize.py)
  ▼
on-prem.staging/upload/anonymized.parquet
  │ (Fabric Data Pipeline copy)
  ▼
OneLake/Files/anonymized/
  │ (01_bronze_load.py)
  ▼
bronze_valuations
  │ (02_silver_enrich.py)
  ▼
silver_valuations_enriched ◄──── public datasets
  │
  │  silver_property_vision ◄──── vision pipeline
  │  (03_gold_features.py joins both)
  ▼
gold_features
  │ (registered as AML data asset, version YYYY.MM.DD)
  ▼
AML training jobs
```

## Refresh cadence

| Layer | Frequency | Trigger |
|---|---|---|
| On-prem extract + anonymize | Weekly | Cron on-prem |
| Bronze load | Triggered on file landing | Fabric Data Pipeline event |
| Silver enrich | Daily | Schedule |
| Vision pipeline | On new property OR weekly batch | Event + schedule |
| Gold features | Daily | Schedule, after silver + vision |
| AML data asset version | Monthly | Pre-retrain step |
