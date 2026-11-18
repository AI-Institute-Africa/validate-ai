# ID / KYC verification

Verify who someone is: a payer submitting proofs of payment, or a staff member or organisation
representative being onboarded. Same contract as the payment engine: **the AI only reads; fixed
rules or a named reviewer decide.** It is **off by default**, it never rejects anyone
automatically, and it never touches the money ledger.

## Flow

```
upload ID (front, back optional) + selfie
  -> malware scan, image check, stored privately                       POST /kyc/verifications
  -> capture quality (size, blur, glare)         unusable?  -> NEEDS_INFORMATION (retake)
  -> find the card, flatten it (Hough lines, contour fallback)
  -> two independent readers (VLM + Tesseract), plus the MRZ when present
  -> cross-source agreement on name / number / birth date / expiry
  -> face match (ID portrait vs selfie) and passive liveness
  -> integrity: tamper score, reused images, same ID number on two people
  -> rules (kyc/auto.py)      clear case -> VERIFIED   anything else -> NEEDS_REVIEW
```

States: `SUBMITTED -> PROCESSING -> VERIFIED | NEEDS_REVIEW | NEEDS_INFORMATION`, then a reviewer
moves `NEEDS_REVIEW` to `VERIFIED`, `REJECTED` or `NEEDS_INFORMATION`. `VERIFIED` ends as
`EXPIRED` after `kyc_validity_days`, or `REJECTED` if a reviewer revokes it. Every outcome is an
append-only `kyc_decisions` row (a database trigger forbids edits) and an audit event.

## Modes (`kyc_auto_verify_mode`)

| Mode | Behaviour |
| --- | --- |
| `off` (default) | People decide everything. The checks still run, so reviewers see scores and reasons. |
| `shadow` | The rules are evaluated and recorded as `SHADOW_WOULD_VERIFY` / `SHADOW_WOULD_REVIEW`, but nothing is verified. Use this to measure on real traffic first. |
| `on` | A case that passes every rule is verified by `rule:kyc-auto`. A sample (`kyc_audit_pct`) goes to a reviewer; the overturn rate is the measure that decides whether to widen it. |

`POPS_KYC_AUTO_DISABLED=true` overrides every organisation. Turning a mode on needs
`kyc_auto_verify_subjects`, `kyc_allowed_doc_types` and `kyc_allowed_countries` (ISO alpha-3, e.g.
`ZWE`); an empty country list means nothing is auto-verified.

## Rules that must all hold for automatic verification

| Blocker code | Rule |
| --- | --- |
| `KILL_SWITCH`, `DISABLED`, `SUBJECT_NOT_ENABLED` | Global switch, mode, and subject type (`payer`, `staff`, `org`) enabled |
| `DOC_TYPE_UNKNOWN` / `_NOT_ALLOWED`, `COUNTRY_UNKNOWN` / `_NOT_ALLOWED` | Accepted document type and issuing country |
| `MRZ_CHECKSUM_FAIL`, `MRZ_REQUIRED` | A found MRZ must pass every check digit; passports must have one (policy can demand it of IDs) |
| `LOW_OCR_AGREEMENT`, `FIELD_CONFLICT` | Two sources agree on the critical fields (a valid MRZ counts as one); no source contradicts another |
| `DOC_EXPIRED`, `DOC_EXPIRES_SOON`, `EXPIRY_UNKNOWN` | Valid for at least `kyc_min_expiry_days` more |
| `NUMBER_FORMAT_INVALID` | National ID number matches the country's format where one is known (South African IDs also pass Luhn) |
| `FACE_UNAVAILABLE`, `FACE_SCORE_LOW` | Cosine similarity at least `kyc_min_face_score` |
| `LIVENESS_UNAVAILABLE`, `LIVENESS_LOW` | Passive liveness at least `kyc_min_liveness` |
| `DOC_TAMPER_SUSPECTED`, `TAMPER_CHECK_SKIPPED` | Tamper score under `tamper_review_score` (uses the receipt forensics) |
| `IMAGE_REUSED_BY_OTHER_SUBJECT`, `ID_NUMBER_USED_BY_OTHER_SUBJECT`, `SELFIE_IS_ID_IMAGE`, `SELFIE_COPIED_FROM_ID_PHOTO`, `MULTIPLE_FACES_IN_SELFIE` | No reused images; one ID belongs to one subject; the selfie is a new photo |
| `READERS_UNAVAILABLE` | A reader outage fails closed to a person |

A capture the subject can fix (too small, blurry, glare, no face found) goes back to them as
`NEEDS_INFORMATION` with a plain-language message, not to a reviewer.

## What KYC gates elsewhere (all off by default)

- `kyc_required_for_auto_approve`: a payment claim is auto-approved only if its payer (`claimant_ref`,
  subject type `payer`) holds a valid verification; otherwise `KYC_NOT_VERIFIED` and a person decides.
  Replay (`/admin/replay`) applies the same rule to past claims.
- `kyc_required_for_staff`: approver-level actions (currently reversals) need the caller to hold a
  valid `staff` verification. **Admins are exempt on purpose** so that enabling it cannot lock
  everyone out. There is no role-granting endpoint in this service (roles come from your identity
  provider), so this is enforced at use, not at grant.

## Separation of duties

Nobody reviews their own identity check, or one they submitted. Staff and organisation checks need
the approver role. Reviewing images is audited (`kyc.evidence_viewed`).

## Privacy

- Images are stored privately under `kyc/<org>/<id>/`, and deleted after `kyc_retention_days`
  (daily task); the row remains with `purged_at` set. Only finished verifications are purged.
- The ID number is kept in `fields` for reviewers and as a **keyed hash** (`doc_number_hash`) for
  duplicate detection. Face embeddings are never stored.
- Extracted values are not logged. Queries are scoped to the caller's organisation, and a submitter
  only sees the status of what they submitted, not the extracted details.
- Treat this as personal data under your local data-protection law: set retention to what you need,
  and get consent wording from your own counsel. This document is not legal advice.

## Models and calibration

- **Document readers**: the VLM reads with an ID-specific schema; Tesseract reads labelled lines
  (English layouts) and, separately, the bottom strip with a restricted alphabet for the MRZ.
  Country templates are data in `app/kyc/templates.py`.
- **Face matching**: `POPS_KYC_FACE_BACKEND=onnx` runs an ArcFace-style ONNX embedding model on CPU.
  **No weights are bundled.** Point `POPS_KYC_FACE_MODEL_PATH` at a model whose licence suits you
  (several popular pretrained face models are licensed for non-commercial research only), and
  `POPS_KYC_FACE_DETECTOR_PATH` at a YuNet ONNX detector (OpenCV Zoo). On OpenCV 4 the bundled Haar
  cascade is the fallback; OpenCV 5 does not ship one. With no model the backend fails closed.
- **Thresholds are not calibrated.** `kyc_min_face_score` (0.45) and `kyc_min_liveness` (0.7) are
  starting points. Run `shadow` mode, compare with reviewers' decisions on your own ID/selfie pairs
  (including ID photos of the kind you really see), and set them from the measured overturn rate.
- **Liveness is passive heuristics v1** (screen-replay pattern, glare, tiny or soft faces, a selfie
  copied from the ID photo). It stops the cheap attacks only; it is not active liveness or depth
  sensing, and the interface (`LivenessChecker`) is there so a stronger model can replace it. A trained
  deepfake and presentation-attack detector is planned (see the section below and
  [`authenticity-detectors.md`](authenticity-detectors.md)).
- The synthetic fixtures in `app/devtools.py` (`make_id_card`, `make_selfie`) and `fake` backends exist
  for tests and demos. `POPS_KYC_FACE_BACKEND=fake` is refused in production.

## API

| Endpoint | Role | Purpose |
| --- | --- | --- |
| `POST /kyc/verifications` | submitter+ | multipart: `subject_type` (`payer`/`staff`/`org`), `subject_ref`, `front`, `selfie`, optional `back` |
| `GET /kyc/verifications/{id}` | submitter (own) / reviewer | status, or full detail for reviewers |
| `GET /kyc/subjects/{type}/{ref}/status` | submitter+ | is this subject verified right now |
| `GET /kyc/review/queue` | reviewer | verifications waiting for a person |
| `POST /kyc/review/{id}/decision` | reviewer | `{"outcome": "VERIFIED"\|"REJECTED"\|"NEEDS_INFORMATION", "note"}` |
| `GET /kyc/verifications/{id}/evidence/{role}` | reviewer | the image (no-store, audited) |
| `GET /kyc/review/auto-verified` | reviewer | automatic verifications, sample and overturn rate |
| `POST /kyc/review/{id}/audit-verdict` | reviewer | `{"verdict": "ok"\|"overturned", "note"}` |

Policy fields are `kyc_*` in the payment policy (`POST /admin/policy`); settings are `POPS_KYC_*`.

## Where the ideas came from

See [`third-party-notices.md`](third-party-notices.md). In short: card-corner detection and the
Tesseract preprocessing follow MIT-licensed projects; the ID-vs-selfie matching approach follows
DocFace; workflow and feature ideas (not code) come from OpenKYC and a commercial SDK's public
description.


## Face matching with InsightFace (optional)

`POPS_KYC_FACE_BACKEND=insightface` uses an ArcFace ONNX model the way it was trained: each face is first
warped so its five landmarks (eyes, nose, mouth corners, from the YuNet detector) land on fixed points in a
112 x 112 picture, then embedded. The plain `onnx` backend crops a loose box instead, which scores lower on
small, old ID photos. Both give a cosine score; the policy threshold `kyc_min_face_score` is a calibrated
number, not a default (see `backend/tools/eval/face_eval.py`).

| Setting | Value |
| --- | --- |
| `POPS_KYC_FACE_BACKEND` | `insightface` |
| `POPS_KYC_FACE_MODEL_PATH` | e.g. `./var/models/w600k_r50.onnx` (from InsightFace's `buffalo_l` pack) |
| `POPS_KYC_FACE_DETECTOR_PATH` | YuNet `face_detection_yunet_*.onnx` (OpenCV Zoo). **Required**: without it the backend refuses to start rather than match worse |

**Licensing.** The InsightFace code is MIT, but its pretrained models are for **non-commercial research
use only**. This project is non-commercial, so that fits; do not reuse the weights in a commercial product
without a licence from InsightFace. Nothing is bundled: you download the files yourself.

**Tested without the weights:** the alignment maths (a rotated, shrunk or moved face is warped back onto the
template) and the fail-closed behaviour. **Not tested:** real accuracy, and that YuNet reports its landmarks
in the order assumed (right eye, left eye, nose, right and left mouth corner, viewed from the image).
Check both once on a few real photos before relying on it.


## Deepfakes, AI clones and presentation attacks (planned)

Today liveness is the passive heuristic above and **there is no deepfake, synthetic-face or presentation-attack
model**. A face-swapped selfie, an AI-generated face or a high-quality screen replay can pass it.

The face detector in [`authenticity-detectors.md`](authenticity-detectors.md) is **built** (it ships with no model, so
it reports `no_model` until you install one). It runs after liveness, trained on our own data and run locally. It reads the aligned face
crop with noise-residual and frequency channels, and combines with the selfie-to-ID embedding drift the face matcher
already computes. It reports `DEEPFAKE_SUSPECTED` or `SYNTHETIC_FACE_SUSPECTED`, which send a verification to
`NEEDS_REVIEW`; it can never move one to `VERIFIED`, and an unavailable model is recorded as skipped, not
as a pass. A detector that did not run changes nothing: the existing rules decide exactly as they did without it, so an
outage never blocks or approves a verification by itself. Both the selfie and the ID portrait are scored, and each score is
recorded with the model's version and hash.

**Per-group fairness is a gate.** A face detector may only escalate after its false-flag rates have been measured by
skin tone, age, lighting and phone class on this deployment's own data, with enough samples in each group to
trust the number. Until then it runs in `shadow` mode. The document-forgery and AI-generated-ID detectors work on the
card image the same way and feed the existing `DOC_TAMPER_SUSPECTED` path.

## National ID numbers: what can and cannot be checked offline

| Country | What we check | Checksum |
| --- | --- | --- |
| South Africa | 13 digits, Luhn check digit, a real birth date, the century (never in the future), sex | Yes (published) |
| Zimbabwe | shape; the check letter (mod 23) is shown to a reviewer as **advisory** only | Community-derived, not official |
| Kenya | 7 or 8 digits; obvious inventions (11111111, 12345678, runs up or down) | **None is published** |
| Ghana Card | `GHA-#########-#`; obvious inventions | **None is published** (the Card has a check character, but its algorithm is not public) |
| Nigeria, Zambia, Tanzania, Uganda | shape; obvious inventions | none used |

A number that fails shape or looks invented goes to a person; it is never rejected automatically, and a
passing number is never described as "verified". Whether the holder exists is a registry question (NIA in
Ghana, IPRS in Kenya) and needs the registry or a licensed provider (Smile ID, uqudo).


## Calibrating the face threshold (what real data we need)

`kyc_min_face_score` (default 0.45) is a starting guess, not a measurement. It must be set from your own
ID-photo and selfie pairs, because faces on small, old, compressed ID photos score lower than benchmark
pairs, and error rates differ by population.

**Collect** (with written consent, stored only for this purpose, deleted afterwards):
- 300 or more *genuine* pairs: a real ID photo and a selfie of the same person, taken the way payers will take them
  (phones in common use, poor light included).
- 3,000 or more *impostor* pairs: the same ID photos paired with selfies of other people. They can be built by
  re-pairing the genuine set. A false-accept rate of 0.1% cannot even be measured with fewer than about 3,000.
- Mix the people the system will really serve (ages, skin tones, glasses, head coverings); report each group
  separately, since one overall number can hide a group the system fails.

**Run** `python backend/tools/eval/face_eval.py --pairs pairs.csv` (columns `card,selfie,same`). It prints false-accept
and false-reject rates by threshold, the AUC with a 95% interval, and how far the chosen threshold moves when the
pairs are resampled. Choose the threshold for the false-accept rate you can live with, and keep auto-verification
in `shadow` mode until the numbers hold on a fresh set. **No real pairs were available while building this, so the
default has not been calibrated.**

## Measuring the tamper check

`python backend/tools/eval/tamper_eval.py --genuine DIR --forged DIR` (or `--demo` for a synthetic self-test).

**What the self-test found.** On synthetic edits (pasted patch, retyped text, inpainting, a re-compressed region, on
flat generated ID cards that were JPEG-saved first) the current tamper analyser separates forged from genuine
no better than chance: AUC about 0.50 (95% interval about 0.39 to 0.61). This set is synthetic and flat, so it does
not say how the check performs on real documents, but it is a clear warning not to rely on it. The check is already
only a *flag* that can route a claim to a person and can never approve or reject one, which is the right place for a
signal this uncertain. Measure it on a labelled real set before trusting its default threshold
(`tamper_review_score` = 0.6) or giving it more weight.

**SIDTD** (European IDs with Crop-and-Replace, inpainted and printed/filmed forgeries) is the natural real set. It
could not be downloaded here (its host is not reachable from this environment). Before using it: check the licence
on its repository record (published sources disagree between CC BY-SA and CC BY-NC-ND), use it for evaluation only,
and do not commit or redistribute any of its images. It contains no African IDs.
