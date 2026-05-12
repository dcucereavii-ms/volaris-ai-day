# Vision Enrichment Pipeline

Scores property condition from licensed internet imagery using Azure OpenAI GPT-4o, and generates CLIP-style embeddings for visual comparable retrieval.

See [../docs/vision-enrichment.md](../docs/vision-enrichment.md) for design.

## Files

- `score_condition.py` — GPT-4o rubric scorer (per image), aggregates per property.
- `embed_clip.py` — produces 1024-d image embeddings via Azure AI Vision multimodal API.
- `requirements.txt` — Python dependencies.

## Run as AML batch job

```powershell
az ml job create -f ../aml/jobs/vision-batch-job.yaml
```

(See pipeline docs for the full batch job YAML — kept out of this MVP for brevity.)

## Cost control

Cache scores in Cosmos DB keyed by `(property_hash, photo_hash)`. Re-score only on photo refresh.
