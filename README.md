# Volaris AI Day — Property Valuation Modernization

End-to-end blueprint for modernizing a legacy on-premises property valuation model using **Microsoft Fabric**, **Azure Machine Learning**, and **Azure OpenAI Vision** — without lifting sensitive bank/insurance data into the cloud in raw form.

> **Scenario**: A data company holds sensitive bank, insurance, and public-registry data on-premises. A property valuation model (last trained in 2009) is stale. We want to retrain with modern techniques, enrich features with public data and internet imagery, and deploy a versioned, A/B-tested endpoint — while preserving data sovereignty.

---

## Solution at a glance

```
ON-PREM                                AZURE
┌──────────────────┐                   ┌──────────────────────────────────────┐
│ Bank/Insurance   │  1. Extract       │  Microsoft Fabric                    │
│ source systems   │  2. Anonymize     │   Lakehouse: bronze → silver → gold  │
│ (raw, sensitive) │  3. Upload───────►│   Data Pipelines / Notebooks         │
└──────────────────┘                   │                                      │
                                       │  Azure ML                            │
┌──────────────────┐                   │   Data assets (versioned)            │
│ Public web       │──Vision──────────►│   AutoML + LightGBM challenger       │
│ Listing photos,  │  pipeline         │   Model Registry (semver)            │
│ Street View,     │  (AOAI GPT-4o +   │   Online Endpoint (blue/green A/B)   │
│ satellite        │   CLIP embeddings)│   Batch Endpoint (nightly)           │
└──────────────────┘                   │   Monitors: drift + quality          │
                                       └──────────────────────────────────────┘
```

Full architecture: [docs/architecture.md](docs/architecture.md)

---

## Repository layout

```
volaris-ai-day/
├── README.md                    # this file
├── docs/                        # design, architecture, mlops, security
├── onprem/                      # extraction + anonymization (runs on-prem)
├── fabric/                      # Lakehouse notebooks + Data Pipelines
├── aml/                         # Azure ML workspace, jobs, endpoints
│   ├── workspace/               # Bicep IaC for AML workspace
│   ├── data/                    # Data asset definitions
│   ├── jobs/                    # AutoML, training, retrain pipeline YAMLs
│   ├── src/                     # Training + scoring Python code
│   └── endpoints/               # Online + batch endpoint YAMLs
├── vision/                      # GPT-4o condition scoring + CLIP embeddings
├── scripts/                     # Upload, promote, rollback utilities
└── .github/workflows/           # CI/CD: lint, deploy, scheduled retrain
```

---

## Quick start

### Prerequisites

- Azure subscription with Owner on a resource group
- Microsoft Fabric capacity (F2+) with a workspace
- Azure CLI ≥ 2.60 with `ml` extension: `az extension add -n ml`
- Python 3.11
- On-prem machine with outbound HTTPS to Azure (or Self-hosted IR / Data Gateway)

### 1. Provision Azure foundation

```powershell
az login
az account set --subscription <SUB_ID>
az group create -n rg-valuation -l westeurope
az deployment group create -g rg-valuation -f aml/workspace/workspace.bicep
```

### 2. Run on-prem anonymization

```powershell
cd onprem
python -m venv .venv; .venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:ANON_SALT = (python -c "import secrets; print(secrets.token_hex(32))")
# Store $env:ANON_SALT in your on-prem secret manager — it must NEVER leave on-prem.
python anonymize.py --input staging\raw_extract.parquet --output staging\upload\
```

### 3. Upload to Azure

```powershell
.\scripts\upload_azcopy.ps1 -SourceDir staging\upload -StorageAccount <acct> -Container anonymized
```

### 4. Build Fabric layers

Import notebooks from `fabric/notebooks/` into your Fabric workspace and run in order:
1. `01_bronze_load.py`
2. `02_silver_enrich.py`
3. `03_gold_features.py`

### 5. Train and deploy

```powershell
# Register the data asset
az ml data create -f aml/data/data-asset.yaml -w aml-valuation-prod -g rg-valuation

# Run AutoML baseline
az ml job create -f aml/jobs/automl-job.yaml -w aml-valuation-prod -g rg-valuation

# Run LightGBM challenger
az ml job create -f aml/jobs/train-lgbm-job.yaml -w aml-valuation-prod -g rg-valuation

# Create online endpoint and deploy blue
az ml online-endpoint create -f aml/endpoints/online-endpoint.yaml
az ml online-deployment create -f aml/endpoints/deployment-blue.yaml --all-traffic
```

### 6. Schedule monthly retraining

```powershell
az ml schedule create -f aml/jobs/retrain-schedule.yaml
```

---

## Key design principles

1. **Data sovereignty first** — raw sensitive data never leaves on-prem; only k-anonymized derivatives upload.
2. **Versioned everything** — data assets, models, code (git tag), endpoint deployments.
3. **Champion/challenger** — every retrain competes against current production on a fixed holdout.
4. **Progressive rollout** — A/B via traffic split (10 → 50 → 100), instant rollback path.
5. **Closed feedback loop** — realized prices flow back via Fabric to drive quality monitors.
6. **Vision is additive** — model degrades gracefully when no photo is available.

---

## Documentation index

| Doc | Purpose |
|---|---|
| [docs/architecture.md](docs/architecture.md) | Component diagram, networking, identities |
| [docs/design.md](docs/design.md) | Data model, feature catalog, model design |
| [docs/data-flow.md](docs/data-flow.md) | Bronze/Silver/Gold lineage and schemas |
| [docs/mlops.md](docs/mlops.md) | Versioning, retraining, A/B, rollback |
| [docs/vision-enrichment.md](docs/vision-enrichment.md) | GPT-4o + CLIP image pipeline |
| [docs/security-and-privacy.md](docs/security-and-privacy.md) | Anonymization, k-anonymity, networking, RBAC |

---

## License

MIT — see [LICENSE](LICENSE).
