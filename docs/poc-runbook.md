# POC Runbook — End-to-End in ~2 hours

A minimal end-to-end run using **synthetic data** so you can demo the full
loop without the on-prem extract or public-data joins.

## What you'll do

1. Generate 50k synthetic property records locally
2. Upload to a Fabric Lakehouse
3. Build the `gold_features` table in Fabric
4. Register it as an Azure ML data asset
5. Train a LightGBM model
6. Deploy to a managed online endpoint (blue)
7. Test the endpoint
8. Train a "v2" challenger and A/B promote
9. (Optional) Schedule monthly retraining

## Prerequisites

| Item | Note |
|---|---|
| Azure subscription, Owner on a resource group | `rg-volaris-poc` |
| Microsoft Fabric capacity (Trial F64 is fine) | Workspace `ws-volaris-poc` |
| Azure CLI ≥ 2.60 | `az extension add -n ml -y` |
| Python 3.11 with this repo cloned | |
| `gh` and `git` (already configured) | |

---

## Step 1 — Generate synthetic data (local, ~30 sec)

```powershell
cd C:\Users\dcucereavii\volaris-ai-day
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install pandas pyarrow numpy
python scripts\generate_synthetic_data.py --rows 50000 --out data\synthetic
```

You should see `data/synthetic/sale_month=YYYY-MM/*.parquet`.

---

## Step 2 — Provision Azure foundation (~5 min)

```powershell
az login
az account set --subscription "<SUBSCRIPTION_ID>"
az group create -n rg-volaris-poc -l westeurope

# Workspace + storage + KV + ACR + AppInsights via Bicep
az deployment group create `
  -g rg-volaris-poc `
  -f aml\workspace\workspace.bicep `
  --parameters workspaceName=aml-volaris-poc
```

> **POC simplification**: For the POC you can edit the Bicep to set
> `publicNetworkAccess: 'Enabled'` on storage and the workspace to skip
> private-endpoint setup. Production uses Private Link.

---

## Step 3 — Create Fabric Lakehouse and upload data (~10 min)

1. Open https://app.fabric.microsoft.com → your workspace `ws-volaris-poc`.
2. **+ New → Lakehouse** → name it `LH_PropertyValuation`.
3. In the lakehouse, click **Files** → **Upload → Upload folder**.
4. Upload `C:\Users\dcucereavii\volaris-ai-day\data\synthetic` so it lands at `Files/synthetic/`.
   - Tip: if the UI is slow, zip the folder and upload + extract with a notebook cell.

---

## Step 4 — Build the gold table (~3 min)

1. In the same lakehouse, **Open notebook → New notebook**.
2. Paste the contents of [fabric/notebooks/00_poc_load_synthetic.py](../fabric/notebooks/00_poc_load_synthetic.py).
3. Run All. You should see three Delta tables created:
   - `gold_features` (full)
   - `gold_features_training`
   - `gold_features_holdout`
4. Note the **OneLake ABFSS path** of `gold_features_training` (right-click → Properties). It will look like:
   ```
   abfss://ws-volaris-poc@onelake.dfs.fabric.microsoft.com/LH_PropertyValuation.Lakehouse/Tables/gold_features_training/
   ```

---

## Step 5 — Register AML data assets (~2 min)

Edit [aml/data/data-asset.yaml](../aml/data/data-asset.yaml) and [aml/data/data-asset-holdout.yaml](../aml/data/data-asset-holdout.yaml) — replace `<FABRIC_WORKSPACE>` with your workspace name and point the `path:` at `gold_features_training` and `gold_features_holdout` respectively.

```powershell
az ml data create -f aml\data\data-asset.yaml `
  --workspace-name aml-volaris-poc -g rg-volaris-poc

az ml data create -f aml\data\data-asset-holdout.yaml `
  --workspace-name aml-volaris-poc -g rg-volaris-poc
```

> **First-time auth**: AML compute needs `Storage Blob Data Reader` on the Fabric workspace's OneLake-backed storage. The simplest POC path is to grant the AML workspace's managed identity that role at the Fabric workspace level.

> **Alternative if Fabric→AML auth is fiddly for the POC**: skip Fabric entirely and upload `data/synthetic/` directly to a regular blob container, then point the data asset at that path.

---

## Step 6 — Train the v1 LightGBM model (~5 min)

```powershell
az ml job create -f aml\jobs\train-lgbm-job.yaml `
  --workspace-name aml-volaris-poc -g rg-volaris-poc `
  --stream
```

When the job finishes:
- Open **Azure ML Studio → Jobs** → check holdout MAPE (~0.10–0.15 expected on synthetic).
- The model is auto-registered as `valuation_lgbm`.

Promote it to the production name:
```powershell
$VERSION = (az ml model list --name valuation_lgbm `
  --workspace-name aml-volaris-poc -g rg-volaris-poc `
  --query "[0].version" -o tsv)

az ml model create --name valuation_prod --version 1 `
  --path "azureml://models/valuation_lgbm/versions/$VERSION" `
  --type mlflow_model `
  --workspace-name aml-volaris-poc -g rg-volaris-poc
```

---

## Step 7 — Create endpoint and deploy blue (~10 min)

```powershell
az ml online-endpoint create -f aml\endpoints\online-endpoint.yaml `
  --workspace-name aml-volaris-poc -g rg-volaris-poc

az ml online-deployment create -f aml\endpoints\deployment-blue.yaml `
  --all-traffic `
  --workspace-name aml-volaris-poc -g rg-volaris-poc
```

Deployment takes 6–10 minutes (image build + instance provisioning).

---

## Step 8 — Test the endpoint (~1 min)

Save this as `data/sample_request.json`:

```json
[
  {
    "geo_h3_r8": "881f1d4807fffff",
    "postcode_prefix": "750",
    "sale_month": "2026-04",
    "property_type": "apartment",
    "size_sqm": 75,
    "rooms": 3,
    "bathrooms": 1,
    "year_built": 1965,
    "size_band": "40-100",
    "log_size_sqm": 4.33,
    "age_years": 61,
    "condition_score": 0.7,
    "roof_condition": 0.7,
    "curb_appeal": 0.7,
    "renovation_flag": 0,
    "has_vision_score": 0
  }
]
```

```powershell
az ml online-endpoint invoke `
  --name valuation-endpoint `
  --request-file data\sample_request.json `
  --workspace-name aml-volaris-poc -g rg-volaris-poc
```

You should get back a price + low/high band JSON.

---

## Step 9 — Retrain a v2 challenger and A/B promote (~10 min)

Simulate "more data arrived" by regenerating with a different seed, re-uploading, and rebuilding the gold table:

```powershell
python scripts\generate_synthetic_data.py --rows 75000 --seed 7 --out data\synthetic_v2
```

Upload `data/synthetic_v2/` to `Files/synthetic/` in the lakehouse (overwriting), re-run the notebook from Step 4, then:

```powershell
# New data asset version
az ml data create -f aml\data\data-asset.yaml `
  --version 2026.05.13 `
  --workspace-name aml-volaris-poc -g rg-volaris-poc

# Train challenger
az ml job create -f aml\jobs\train-lgbm-job.yaml --stream `
  --set inputs.data=azureml:gold_features:2026.05.13 `
  --workspace-name aml-volaris-poc -g rg-volaris-poc

# Register as valuation_prod v2
$V2 = (az ml model list --name valuation_lgbm --query "[0].version" -o tsv `
  --workspace-name aml-volaris-poc -g rg-volaris-poc)
az ml model create --name valuation_prod --version 2 `
  --path "azureml://models/valuation_lgbm/versions/$V2" `
  --type mlflow_model `
  --workspace-name aml-volaris-poc -g rg-volaris-poc

# Deploy as green pointing at v2
az ml online-deployment create -f aml\endpoints\deployment-green.yaml `
  --set model=azureml:valuation_prod:2 `
  --workspace-name aml-volaris-poc -g rg-volaris-poc

# 10/90 split
.\scripts\promote.ps1 -Endpoint valuation-endpoint `
  -Workspace aml-volaris-poc -ResourceGroup rg-volaris-poc -GreenPct 10

# Hit the endpoint a few times — observe split in Studio → Endpoints → Metrics
1..20 | ForEach-Object {
  az ml online-endpoint invoke --name valuation-endpoint `
    --request-file data\sample_request.json `
    --workspace-name aml-volaris-poc -g rg-volaris-poc | Out-Null
}

# Full promotion
.\scripts\promote.ps1 -GreenPct 100 `
  -Endpoint valuation-endpoint -Workspace aml-volaris-poc -ResourceGroup rg-volaris-poc

# (or instant rollback if something looks wrong)
.\scripts\rollback.ps1 -Endpoint valuation-endpoint `
  -Workspace aml-volaris-poc -ResourceGroup rg-volaris-poc
```

---

## Step 10 — (Optional) Schedule monthly retrain

```powershell
az ml schedule create -f aml\jobs\retrain-schedule.yaml `
  --workspace-name aml-volaris-poc -g rg-volaris-poc
```

This kicks the [retrain-pipeline.yaml](../aml/jobs/retrain-pipeline.yaml) on the first Monday of every month at 03:00 UTC. The pipeline only registers the new model if the promotion gates in [aml/src/conditional_register.py](../aml/src/conditional_register.py) pass.

---

## Cleanup

```powershell
az ml online-endpoint delete --name valuation-endpoint --yes `
  --workspace-name aml-volaris-poc -g rg-volaris-poc
az group delete -n rg-volaris-poc --yes --no-wait
# Delete the Fabric workspace from the portal.
```

---

## Demo talking points

| Step | What to highlight |
|---|---|
| 1–2 | "Real data never leaves on-prem; for POC we use synthetic in the same shape." |
| 3–4 | "Fabric is the open lakehouse layer; AML reads OneLake directly with no copy." |
| 5–6 | "Versioned data asset → reproducible training; LightGBM beats AutoML on tabular." |
| 7–8 | "Managed endpoint = autoscale, AAD auth, data collection for monitoring." |
| 9 | "Blue/green = zero-downtime promotion; instant rollback on regression." |
| 10 | "Promotion gates prevent silent quality regressions on auto-retrain." |
| Bonus | "Vision pipeline (GPT-4o) plugs in as an additional Silver table — model degrades gracefully when no photo." |
