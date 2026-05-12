# On-Prem Anonymization

Runs entirely **on-premises**. The output (`staging/upload/`) is the only artifact that may move to Azure, **after** privacy review sign-off.

## Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Generate and store the salt

The salt is a long random secret used for hashing `property_id`. **It must never leave on-prem.**

```powershell
$env:ANON_SALT = (python -c "import secrets; print(secrets.token_hex(32))")
# Store in your on-prem secrets vault. Required for every run.
```

## Extract

Use [extract.sql](extract.sql) as a starting template. Adjust to your schema. Output a Parquet file at `staging/raw_extract.parquet`.

## Anonymize

```powershell
python anonymize.py --input staging/raw_extract.parquet --output staging/upload/
```

The script:
1. Drops direct identifiers.
2. Hashes `property_id` with the on-prem salt.
3. Generalizes lat/lon → H3 r8, postcode → 3-char prefix, sale date → month.
4. Applies k-anonymity with k=10 and drops the long tail.
5. Writes Parquet partitioned by `sale_month`.

## Validate before upload

The script prints:
- Row count delta
- k-anon group-size distribution
- Schema summary

Have your privacy officer review and sign off before running [../scripts/upload_azcopy.ps1](../scripts/upload_azcopy.ps1).
