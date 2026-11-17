# Training data from reviewer corrections

Every time a reviewer corrects a field, the engine keeps the model's reading and the correction (who,
why, when). With consent, those pairs are the best labelled data for fine-tuning the readers on real
Zimbabwean receipts and IDs, with no separate labelling job.

## Consent first

Nothing is exported unless the organisation's policy records consent:

- `training_export_consent: true`
- `training_consent_ref`: the reference of the written agreement (for example `AGR-2026-014`)

Both are off by default. Publishing a policy that turns them on goes through the usual "I understand" step.
Without them `GET /admin/training/corrections` returns 403 `CONSENT_MISSING` and the script refuses to run.

## What is exported

One JSON line per corrected field: the evidence SHA-256 and content type, the field name, the model's reading
and which model gave it (name and version), its confidence, the corrected value, the reason and when. **No
images and no names**; the files can be fetched separately, under the same consent, from secure storage using
the SHA-256. Every export writes a `training.exported` audit event with the row count and consent reference.

```bash
# API (admin): newline-delimited JSON
GET /admin/training/corrections?since=2026-11-01T00:00:00Z

# or from the command line
cd backend && python scripts/export_corrections.py --org <org uuid> --out corrections.jsonl
```

## Using it

1. Collect corrections during the shadow pilot; keep a held-out set of real layouts that is never trained on.
2. Benchmark the starting model with `backend/scripts/benchmark_reader.py --card CARD.md`.
3. Fine-tune (`scripts/train_extractor.py` for Donut, or an open vision-language model on our own servers).
4. Fill in a model card (`docs/model-cards/TEMPLATE.md`), run in watching mode, replay, then switch on.

The synthetic sample set only checks the training pipeline; it is never used to claim accuracy.
