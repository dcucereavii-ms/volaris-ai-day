# Architecture

## Components

| Layer | Service | Purpose |
|---|---|---|
| Source | On-prem RDBMS (SQL Server / Oracle / PostgreSQL) | System of record for sensitive valuations |
| Anonymization | On-prem Python job | Strip identifiers, generalize quasi-IDs, k-anonymity check |
| Transport | Self-hosted IR or AzCopy over Private Link | Move anonymized parquet to Azure |
| Lake | OneLake (Microsoft Fabric Lakehouse) | Bronze/Silver/Gold delta tables |
| Enrichment | Fabric Notebooks (PySpark) | Join public datasets, geospatial features |
| Vision | Azure OpenAI (GPT-4o) + Azure AI Vision | Property condition scoring from images |
| Vector | Azure AI Search (vector index) | Visual comparable retrieval |
| Training | Azure ML (AutoML + custom LightGBM) | Champion/challenger training |
| Registry | Azure ML Model Registry | Versioned models with approval gates |
| Serving | Azure ML Managed Online Endpoint | Real-time API, blue/green deployments |
| Batch | Azure ML Batch Endpoint | Nightly portfolio revaluation |
| Monitoring | Application Insights + AML Monitors | Drift, quality, latency alerts |
| Orchestration | Azure ML Pipelines + Schedules | Monthly retrain |
| CI/CD | GitHub Actions | Lint, deploy, scheduled triggers |

## Network

- **Private Endpoints** for Storage, Key Vault, ACR, AML workspace.
- **AML Managed VNet** with `allow_internet_outbound` (for AOAI calls) — restrict via FQDN rules.
- **No public IPs** on compute clusters.
- On-prem egress restricted to known Azure service tags.

## Identity

- Workspace **system-assigned managed identity** with:
  - `Storage Blob Data Reader` on Fabric OneLake-backed ADLS
  - `AcrPull` on shared ACR
  - `Cognitive Services User` on Azure OpenAI resource
- **Entra ID** for endpoint auth (`auth_mode: aad_token`); no shared keys in production.
- **Workload identity** federation for GitHub Actions → Azure (no long-lived secrets).

## Diagram

```
┌──────────────── ON-PREM ────────────────┐    ┌──────────────────────── AZURE ────────────────────────┐
│                                         │    │                                                       │
│  ┌─────────┐   ┌──────────────┐         │    │  ┌─────────────┐    ┌────────────────────────────┐   │
│  │ Source  │──►│ Anonymizer   │─parquet─┼────┼─►│  ADLS Gen2  │◄───│ OneLake shortcut (Fabric)  │   │
│  │ DB      │   │ (k-anon, H3) │         │    │  │  (private)  │    └─────────────┬──────────────┘   │
│  └─────────┘   └──────┬───────┘         │    │  └─────────────┘                  │                  │
│                       │ salt vault       │   │                                    ▼                  │
│                       └─ stays on-prem   │   │              ┌──────────── Fabric Lakehouse ─────┐   │
│                                          │   │              │ bronze → silver(+public) → gold   │   │
└──────────────────────────────────────────┘   │              └────────────────┬──────────────────┘   │
                                               │                               │                      │
┌──────── PUBLIC WEB ────────┐                 │                               ▼                      │
│ Listing / Street View /    │──photos────────►│   ┌───────────┐    ┌──────────────────────────┐     │
│ Sentinel-2                 │                 │   │ AOAI      │───►│  Azure ML Workspace      │     │
└────────────────────────────┘                 │   │ GPT-4o +  │    │  ┌────────────────────┐  │     │
                                               │   │ embeddings│    │  │ Data assets (vN)   │  │     │
                                               │   └───────────┘    │  │ AutoML + LGBM jobs │  │     │
                                               │                    │  │ Model registry     │  │     │
                                               │                    │  └─────────┬──────────┘  │     │
                                               │                    │            ▼             │     │
                                               │                    │  ┌────────────────────┐  │     │
                                               │                    │  │ Online Endpoint    │  │     │
                                               │                    │  │  blue ◄──A/B──► gn │  │     │
                                               │                    │  ├────────────────────┤  │     │
                                               │                    │  │ Batch Endpoint     │  │     │
                                               │                    │  └─────────┬──────────┘  │     │
                                               │                    │            ▼             │     │
                                               │                    │  ┌────────────────────┐  │     │
                                               │                    │  │ Monitors + AppIns  │──┼─►alerts
                                               │                    │  └────────────────────┘  │     │
                                               │                    └──────────────────────────┘     │
                                               └───────────────────────────────────────────────────────┘
```
