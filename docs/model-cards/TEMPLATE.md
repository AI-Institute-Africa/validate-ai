# Model card: <name and version>

Fill one in for every model version that runs in production, and keep it with the release.

| Field | Value |
| --- | --- |
| Purpose | reading receipts / reading IDs / template recogniser / fake-receipt scorer / ID forgery / face deepfake / near-duplicate / AI-text |
| Base model and licence | name, source, licence text checked (yes/no, date) |
| How it was obtained | downloaded as released / fine-tuned from <base> / trained from scratch |
| Where it runs | host and region (must be a host we control) |
| Version string recorded on decisions | e.g. `ollama:qwen2.5vl:7b` |
| Training data | consent reference, number of documents, date range, how labelled |
| Held-out test set | size, how it was kept separate from training |

## Accuracy on the held-out set

| Template or document type | Documents | Amount | Reference | Date | Currency | Notes |
| --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  |

Produced with `backend/scripts/benchmark_reader.py` (`--card` writes this table).

## Faces and ID documents (if applicable)

Results by document type (older metal-laminated ID, polycarbonate ID, passport, licence) and on
Zimbabwean faces: false-accept and false-reject rates at the chosen threshold, number of pairs.

## Authenticity detectors (if applicable)

Fill in for the models in `docs/authenticity-detectors.md`. State the test set for every number.

| Item | Value |
| --- | --- |
| Detector and mode | receipt / doc / face / duplicate / text; `off` / `shadow` / `escalate` |
| Model file, SHA-256, size, latency | measured on 4 CPU cores |
| Training recipe | from scratch or pretrained backbone (source, licence, SHA-256); self-supervised pretraining (yes/no); one-class model (yes/no); distilled and quantised (yes/no) |
| Data used | synthetic generators, confirmed fakes (consent ref), public datasets (approved licences) |
| Held-out real set | size, how separated (claim, payer, time) |
| AUC with 95% interval | on the frozen benchmark, on the real held-out set, on the evasion split |
| Threshold chosen | the target false-flag rate it was set for, and the measured rate and recall |
| Calibration | method, and the abstain ("uncertain") rate |
| Per-generator results | AUC or recall for each synthetic generator and each public set, so overfitting to a generator is visible |
| Per-group results (faces) | skin tone, age, lighting, phone class: sample count, false-flag rate, recall; gaps and any group too small to measure |
| Drift and self-test | last self-test date and result |
| Acceptance gates met | list each gate from `authenticity-detectors.md` and yes/no |

## Known limits

Layouts it has not seen, worn or glared documents, phones and lighting where it fails.

## Sign-off

Reviewed by, date, decision (use in watching mode / use / do not use).
