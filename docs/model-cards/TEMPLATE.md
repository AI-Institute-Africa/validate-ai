# Model card: <name and version>

Fill one in for every model version that runs in production, and keep it with the release.

| Field | Value |
| --- | --- |
| Purpose | reading receipts / reading IDs / template recogniser / fake-receipt scorer |
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

## Known limits

Layouts it has not seen, worn or glared documents, phones and lighting where it fails.

## Sign-off

Reviewed by, date, decision (use in watching mode / use / do not use).
