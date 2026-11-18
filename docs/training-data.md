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


# Training the authenticity detectors

The same consent rules cover the data for the trained detectors in
[`authenticity-detectors.md`](authenticity-detectors.md). Everything below runs **offline on the customer's own
machine**: a laptop (CPU, small data, resumable with `--max-minutes` and checkpoints) or a private GPU server.
Datasets and weights live under `./var/` and are never uploaded; no API is called.

## Where the labels come from

| Source | Label | Notes |
| --- | --- | --- |
| Genuine receipts, IDs and selfies already in the system | genuine (unlabelled for self-supervised pretraining) | Same consent gate as corrections. Hashes first; files fetched from storage under the same consent. |
| Reviewer outcomes: `confirmed_fake` and `false_positive` alerts, rejections as `TAMPERED_DOCUMENT` or `DUPLICATE_CONFIRMED` | fake / genuine | The most valuable labels. A false positive is as useful as a confirmed fake: it teaches the model what *not* to flag. |
| **Synthetic fakes we generate** | fake, with the generator recorded | Pasted or inpainted patches, retyped text, re-renders, double JPEG, screen capture, resampling artefacts; for faces: blend or warp swaps, screen replay, print. A model trained on these learns these generators; report its results per generator and never as real-world accuracy. |
| **Public research datasets** | fake / genuine | **Each licence must be approved by the owner before download** and is listed in `docs/third-party-notices.md`. Evaluation-only datasets are never trained on. |

`python -m training.detect.export_confirmed` (or `GET /admin/training/detector-labels`) writes evidence SHA-256 and content type,
the label (`fake` for a confirmed fake, `genuine` for a false positive), the risk signals, when it was decided and what the trained
detectors scored at the time, so cases where a detector and a person disagreed can be labelled first. **No images and no names**; every export is audited
(`training.exported`).

## Method (summary; the full reasons are in `authenticity-detectors.md`)

1. **Self-supervised pretraining** on unlabelled genuine documents (contrastive learning), so the backbone learns our domain.
2. **Supervised head** on synthetic and confirmed fakes, with forensic input channels (noise residual, frequency
   spectrum, ELA) and evasion-style augmentations (re-compression, screenshot-of-screenshot, noise, resizing).
3. **One-class model** on genuine documents only, so unseen forgery types still look unlike genuine.
4. **Metric-learning embedding** for near-duplicates, with same-template, different-amount receipts as hard negatives.
5. **Calibration** on a held-out set, then **conformal** thresholds so the model can answer "uncertain".
6. **Active learning**: the next batch to label is the most uncertain and most disputed cases.
7. **Compression**: distil to a small student, export ONNX, quantise to int8; measure what compression cost.

## Splits that keep the numbers honest

- A **frozen benchmark** that is never trained on and never changes between model versions, so versions can be compared.
- A **held-out set of real documents from this deployment**, kept separate by claim, payer and time (never random
  rows from the same payer), because near-identical receipts leak between random splits.
- An **evasion split** built only from re-compressed, re-photographed and noised copies.
- For faces, **per-group** tables (skin tone, age, lighting, phone class) with sample counts.

## Retraining and promotion

A retrain produces a new versioned model file and model card. It is compared with the current model on the frozen
benchmark and the held-out real set, and is promoted only if it is better and no per-group gap widens. The previous
file is kept, so rollback is replacing the file. A periodic self-test generates fresh synthetic fakes with the current
generators and checks the live model still flags them; a drop is reported through the ops outbox.

## Running it

Two tracks. The **classical** one needs only numpy and runs and is tested everywhere. The **deep** one needs PyTorch and
has **not been run in the build environment**: run it with `--smoke` first.

```bash
cd backend

# the whole classical loop on fictional demo documents, nothing downloaded (about 2 minutes for 240 receipts)
python -m training.detect.demo_loop --kind receipt --out ../var/detect-demo --n 240

# or step by step, on your own genuine pictures
python -m training.detect.build_dataset --kind receipt --out ../var/detect/data --source-dir /path/to/genuine/
python -m training.detect.train_linear  --data ../var/detect/data --kind receipt --out ../var/models/detect
python -m training.detect.evaluate      --data ../var/detect/data --kind receipt \
       --model ../var/models/detect --card model-card-receipt.md

# the deep track (heavy; a laptop CPU works for small data, a GPU is faster)
pip install -e ".[detect-train]"
python -m training.detect.train_cnn --data ../var/detect/data --kind receipt --out ../var/models/detect --smoke
python -m training.detect.train_cnn --data ../var/detect/data --kind receipt --out ../var/models/detect --max-minutes 90

# then point the engine at the folder, in shadow mode first
POPS_DETECT_MODEL_DIR=../var/models/detect POPS_DETECT_MODE=shadow
```

What the scripts do, and what to read in their output:

- `build_dataset` writes genuine pictures and synthetic forgeries made from each (generators in `training/detect/synth.py`), and an
  index. Splits are made later, **by source**, so a forgery never lands in a different part from its original.
- `train_linear` standardises, adds a genuine-only distance, fits a logistic regression, calibrates on the held-out calibration part,
  picks the escalation threshold for a stated false-flag rate (`--max-false-flag`, default 5%) and the uncertainty band
  (`--alpha`, default 0.1), trains on evasion-style copies unless `--no-augment`, and writes `linear_<kind>.npz` and a `manifest.json`
  entry carrying the file's SHA-256. `--max-minutes` bounds the run.
- `evaluate` measures the test part and the evasion set, with the existing tamper check beside it, and writes a model card. **Read the banner:**
  results on synthetic data are not real-world accuracy, and a card from them keeps the detector in `shadow` mode.
- `train_cnn` pretrains on the genuine pictures without labels, fine-tunes, calibrates with the same code as `train_linear`, exports ONNX
  with the calibration inside, and refuses to install a model whose ONNX output differs from PyTorch's. It resumes from a checkpoint.
