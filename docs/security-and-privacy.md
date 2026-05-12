# Security and Privacy

## Data sovereignty

| Data class | Location | Cloud movement |
|---|---|---|
| Raw bank/insurance records | On-prem only | Never |
| Anonymization salt | On-prem secret manager | Never |
| Original `property_id` ↔ `property_hash` mapping | On-prem only | Never |
| Anonymized + generalized parquet | Cloud (after sign-off) | Yes, encrypted |
| Public datasets | Cloud | Free movement |
| Vision features | Cloud | Yes |
| Model artifacts | Cloud | Yes |

## Anonymization scheme

1. **Drop direct identifiers**: name, owner ID, account number, street address, phone, email.
2. **Pseudonymize join keys**: `property_id` → `SHA-256(salt || id)[:16]`. Salt stays on-prem.
3. **Generalize quasi-identifiers**:
   - lat/lon → H3 resolution 8 (~0.7 km² hexagons)
   - postcode → first 3 chars
   - sale date → month
   - size → 10 m² bands (optional)
4. **k-anonymity**: every quasi-identifier combo appears ≥ k=10 times. Drop the long tail.
5. **Optional differential privacy**: ±0.5% Laplace noise on `sale_price` if DPO requires.

Validation steps before upload:
- Row-count delta logged
- k-anon proof report archived
- DPO/legal sign-off ticket attached to dataset version

## Networking

| Resource | Public access | Private endpoint |
|---|---|---|
| ADLS Gen2 (anonymized landing) | Disabled | Yes |
| Fabric workspace | Conditional Access | Yes (when GA) |
| AML workspace | Disabled | Yes |
| Key Vault | Disabled | Yes |
| ACR | Disabled | Yes |
| Online endpoint | Enabled (auth required) | Optional Private Link |
| Azure OpenAI | Disabled | Yes |

On-prem egress: outbound to specific Azure service tags only, no general internet.

## Identity & access

- **Entra ID** for all human and workload auth.
- **Managed identities** for AML compute → Storage / Key Vault / AOAI / ACR.
- **Workload identity federation** for GitHub Actions → Azure (no client secrets).
- **Endpoint auth**: `aad_token` mode, scoped to caller groups.
- **RBAC roles** (least privilege):
  - Data engineers: `Storage Blob Data Contributor` on bronze/silver containers
  - ML engineers: `AzureML Data Scientist`
  - Approvers: `AzureML Compute Operator` + manual approval gate in pipeline
  - Operators: read-only on registry, deployment update permission

## Secrets

| Secret | Storage | Rotation |
|---|---|---|
| Anonymization salt | On-prem HashiCorp Vault / AKV (on-prem mode) | Annual, with re-anonymization |
| AOAI key (if used) | Azure Key Vault, referenced by managed identity | Quarterly |
| AML endpoint keys | Avoid; use AAD tokens | n/a |
| GitHub → Azure | Workload identity federation, no secrets | n/a |

## Audit

- All data plane operations on Storage and Key Vault logged to **Log Analytics**.
- AML jobs traced in workspace + App Insights.
- Endpoint requests logged with **data collector** to storage (model_inputs + model_outputs).
- Retention: 1 year hot, 7 years cold (compliance).

## Compliance posture

| Regime | Coverage approach |
|---|---|
| GDPR (EU) | Lawful basis = legitimate interest; DPIA on anonymization; no personal data in cloud |
| Banking secrecy | Contractual review per jurisdiction; anonymization sign-off per dataset |
| Sector regulators | Annual penetration test, model risk management documentation |

## Threat model (selected)

| Threat | Mitigation |
|---|---|
| Re-identification of anonymized data | k-anonymity ≥ 10, generalization, no rare quasi-ID combos shipped |
| Model inversion attack on endpoint | Rate limiting, output rounding to nearest €500, no raw probabilities exposed |
| Salt leakage | Salt never leaves on-prem; rotated on incident |
| Image PII leakage (faces, plates) | Azure AI Vision face/plate redaction before storage |
| Prompt injection in vision model | JSON-mode response, validation schema, ignore text-in-image instructions |
