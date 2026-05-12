# MLOps

## Versioning

| Asset | Scheme | Example |
|---|---|---|
| Data asset | `YYYY.MM.DD` snapshot date | `gold_features:2026.05.12` |
| Model | Semver `MAJOR.MINOR.PATCH` | `valuation_prod:2.3.1` |
| Endpoint deployment | `blue` / `green` | A/B slots |
| Code | Git tag aligned to model | `model-v2.3.1` |
| Container image | Git SHA | `aml-score:7f3a2b1` |

Required model registry tags: `data_version`, `git_sha`, `training_job_id`, `holdout_mape`, `approved_by`.

## Retraining pipeline

Defined in [aml/jobs/retrain-pipeline.yaml](../aml/jobs/retrain-pipeline.yaml). Steps:

1. **refresh_data** — re-export anonymized snapshot from on-prem (manual approval), refresh gold table, register new data asset version.
2. **train_challenger** — LightGBM with current best hyperparameters from prior run.
3. **evaluate** — score challenger and current champion on identical fixed holdout. Compute global + slice MAPE.
4. **conditional_register** — promote only if all gates pass.

## Promotion gates

A challenger is promoted only if **all** of the following hold:

| Gate | Threshold |
|---|---|
| Global MAPE improvement | ≥ 2% relative |
| Worst-region MAPE regression | ≤ 5% relative |
| Worst-property-type MAPE regression | ≤ 5% relative |
| Calibration (predicted vs actual) | Mean ratio in [0.97, 1.03] |
| Inference latency p95 | ≤ champion p95 + 50 ms |
| Explainability available | Yes |

If any gate fails → log + notify, do not register.

## A/B testing

```powershell
# Deploy challenger to green slot
az ml online-deployment create -f aml/endpoints/deployment-green.yaml

# Progressive traffic shift
az ml online-endpoint update --name valuation-endpoint --traffic "blue=90 green=10"
# After 3 days of clean metrics:
az ml online-endpoint update --name valuation-endpoint --traffic "blue=50 green=50"
# After 1 week:
az ml online-endpoint update --name valuation-endpoint --traffic "blue=0 green=100"
```

**A/B comparison signals**:
- Latency p50/p95/p99 (App Insights)
- Prediction distribution KS-test between blue and green
- Error rate, throttling
- Realized accuracy when ground-truth sale prices arrive (joined back via `property_hash`)

After full promotion, swap names: green → blue. Keep old version in registry for 90 days as rollback target.

## Rollback runbook

See [scripts/rollback.ps1](../scripts/rollback.ps1).

Triggers:
- Error rate > 1% for 5 minutes
- p95 latency > 2× baseline for 10 minutes
- Prediction distribution drift score > 0.3
- Manual override

Action:
```powershell
az ml online-endpoint update --name valuation-endpoint --traffic "blue=100 green=0"
```
Instant. Then triage offline.

## Monitoring

Configured via Azure ML Monitors:

| Monitor | Metric | Frequency | Action |
|---|---|---|---|
| Data drift | PSI per feature vs training | Weekly | Alert if PSI > 0.2 |
| Prediction drift | KS-test on output distribution | Daily | Alert if p < 0.01 |
| Model quality | MAPE on labeled feedback | Weekly | Alert if MAPE > champion + 5% |
| Endpoint health | Latency, error rate | 1 min | PagerDuty/Teams |

Feedback loop: Fabric pipeline joins logged predictions with realized sale prices (when transactions complete). Output → `gold_predictions_with_actuals` → drives quality monitor + next retrain training data.

## Cost guardrails

- AutoML jobs: max 4h, max 50 trials.
- Online endpoint: autoscale 2–8 instances, scale-down after 5 min idle.
- AOAI vision: cache scores per `property_hash + photo_hash` (Cosmos DB).
- Set Azure Cost Management budget + alerts on the resource group.
