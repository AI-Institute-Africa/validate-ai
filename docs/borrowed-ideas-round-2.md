# What we took from the face, ID and proof-of-payment repos

The project is **not for commercial use**. Rule kept: MIT code may be depended on; anything without a
licence, or non-MIT, is ideas only and nothing is copied. Everything below was written fresh.

## Built
| Idea | From | Where |
| --- | --- | --- |
| National ID number checks (ZA check digit, real birth date, century that is never in the future; ZW check letter) | adieyal/id_validation (MIT) | `backend/app/kyc/idnumbers.py`. The Zimbabwe letter scheme is community-derived, so it is **advisory** (shown to a reviewer as `id_number` check) and never changes an outcome |
| Provider adapters with typed failures, answers must match the asked reference, one result per item in a batch | unified-receipt-verifier (MIT) | `backend/app/providers/`, `POST /providers/verify-batch` (reviewer only, `decision_effect: none`). Only EcoCash's reference shape is known; other providers have no guessed pattern. No transport is configured, so nothing calls out until an official API/webhook is wired in |
| Calibrating the face threshold on your own pairs, and saying when there are too few pairs to measure a low error rate | deepface threshold tables (MIT, idea) | `backend/app/kyc/calibration.py`, `backend/tools/eval/face_eval.py` |

## Already in Validate (not rebuilt)
Quote-grounding of reader output, one credit per provider transaction, idempotent allocations,
duplicate-file hash, injection guardrails, "AI reads, rules decide".

## Decided against
face_recognition (weaker, no liveness), CompreFace as a dependency (heavy, no liveness), FaceOnLive
OpenKYC (no licence, compiled front end), idanalyzer (paid, sends images out), AI-KYC-System,
kyc-check, kyc-validation-api, Passport-Verification-System, MiniAiLive, Temporal (new infrastructure
for what the review queue already does), id-verifier (JavaScript, mDL not yet relevant here).

## Later, if wanted
InsightFace as an optional face backend (code MIT; its pretrained weights are for non-commercial
research, which fits this project); SIDTD as an evaluation set for the tamper check (European IDs
only; confirm its licence first); a trusted-payee check per organisation.
