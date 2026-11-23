# Data collection plan for training the models

This plan says what data each model needs, how much, where it comes from, who labels it and in
what order. It covers every model in the platform: the readers, the document-type classifier, the
authenticity detectors, the KYC face and ID models, and the fraud risk scorer.

It builds on [`training-data.md`](training-data.md) (consent and export),
[`authenticity-detectors.md`](authenticity-detectors.md) (detector design and acceptance gates),
[`models.md`](models.md) (reader models) and blueprint §12 (when to train at all).

> **The quantities below are starting targets, not guarantees.** They are what is usually needed to
> measure a model honestly, so the first purpose of the data is to **measure**. Train only where a
> measurement says a model is below target (blueprint §12.1).

## 0. Before collecting anything (weeks 0–2)

### 0.1 Act now: real receipts are committed to the repository

`sample_data/real PoPs/` holds 84 real proofs of payment (20 PDFs and 64 images). Their file names
include payers' names and amounts. They are in git history, so anyone with access to the
repository has a copy.

1. The data owner decides whether these files were shared with consent for this purpose.
2. Whatever the answer, move them to the secure dataset store (section 6). Delete them from the
   repository, and ask the repository owner whether to purge them from history as well. Purging
   rewrites history, so it is the owner's call.
3. If consent exists, they become the first 84 items of the **frozen benchmark** (section 5), not
   training data. Real receipts are scarcer than training examples.

### 0.2 Governance sign-offs

| Item | Who | Output |
| --- | --- | --- |
| Data-protection review (Cyber and Data Protection Act, blueprint §4.3) | DPO and legal | Written approval of purpose, retention and access |
| Payer consent wording on upload, WhatsApp and KYC screens (English, Shona, Ndebele) | DPO, translators | Notice text live and its version bumped (each claim stores the version the payer saw in `consent_version`) |
| Organisation agreement for training use | Data owner | `training_export_consent: true` and `training_consent_ref` set in the policy |
| Licence approval for any public dataset or pretrained weights | Data owner | Entry in `docs/third-party-notices.md` |
| Named roles (section 7) | Project lead | Names in the tracker |

Nothing is exported until these are done. The export tools refuse to run without the consent
policy.

## 1. The models and what each one needs

| # | Model | Train or only measure? | Data unit | Label | Starting target | Main source |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | **Receipt reader (VLM)**: Qwen-VL / Gemma via Ollama, LoRA later | Measure first, fine-tune only if below target | One proof (image, PDF, SMS text) | `ReceiptFields`: provider, document_type, transaction_id, amount, currency, date, sender, beneficiary, status | **300+** to benchmark; **200–300 per major layout** to fine-tune; **150+** held out | Historical backlog matched to statements; reviewer corrections |
| 2 | **Second reader (OCR)**: Tesseract, or PaddleOCR as its replacement | Measure; swap engines on evidence | Same proofs | Same fields (OCR is scored on the same benchmark) | Same set as #1 | Same as #1 |
| 3 | **Document-type classifier** (small CNN / Florence-2) | Train | One proof | `document_type` + provider | **100+ per class**, ~10 classes | Falls out of #1's labels |
| 4 | **Near-duplicate embedding** | Train (metric learning) | Pairs of proofs | same payment / different payment | **500+ genuine proofs**, each recaptured 2–4 ways; hard negatives of the same template with a different amount | Recapture sessions; synthetic transforms |
| 5 | **Receipt forgery / AI-generated detector** | Train (classical first, then CNN), shadow only | One proof | genuine / fake (+ generator) | **1,000+ genuine sources**; every confirmed fake; synthetic fakes ×3 per source | Backlog (genuine); red-team fakes; confirmed fakes |
| 6 | **ID document reader** (VLM + Tesseract + MRZ) | Measure; tune templates | ID card / passport photo | `IdFields` + MRZ | **100+ per document type** (old metal ID, plastic ID, passport, licence) | Consented staff and volunteer IDs; KYC pilot |
| 7 | **ID forgery / AI-generated detector** | Train, shadow only | ID photo | genuine / fake | **300+ genuine per type**; red-team fakes | Same as #6, plus red team |
| 8 | **Face match threshold** (ArcFace-style, pretrained) | Calibrate only (no training) | ID portrait + selfie pair | same / different person | **300+ genuine pairs**, **3,000+ impostor pairs** (re-paired) | Consented KYC pilot volunteers |
| 9 | **Face deepfake / presentation-attack detector** | Train, shadow only | Selfie | live / replay / print / swap / synthetic | **1,000+ live selfies** across groups; **300+ attacks** per attack type | Volunteers; red-team attack sessions |
| 10 | **Fraud risk scorer** (gradient-boosted, after shadow mode) | Train | One decided claim | admin outcome: `confirmed_fake` / `false_positive`, plus rejection reasons | **100+ confirmed fakes** and **1,000+ cleared claims** before training; until then, tune signal weights | Admin decisions in the console (`GET /admin/accuracy`) |
| 11 | **AI-written text classifier** (optional) | Defer | Pasted text | human / AI-written | Not planned until 1–10 run | — |

**Not models, but they need the same samples:**
- provider receipt templates and statement profiles: at least **20 real examples per provider**;
- SMS/email alert templates: at least **20 real alerts per provider**.

These are rules, and the examples come from the same collection runs. See
`sample_data/zw/README.md`.

## 2. Coverage: what the set must span

A model is only measured on what it has seen. Track counts in each cell. A cell under its minimum
is a **gap** to fill before training, not after.

| Dimension | Values | Minimum per value (benchmark) |
| --- | --- | --- |
| Provider / channel | EcoCash, OneMoney, InnBucks, O'mari, Mukuru, CBZ, Stanbic, FBC, ZB, CABS, NMB, Steward, Ecobank, remittance apps (e.g. Remitly), card/gateway receipts | 20 (40 for the top 3 by volume) |
| Format | in-app screenshot, photo of a phone screen, photo of a paper slip or deposit slip, bank PDF, SMS text, forwarded email, WhatsApp-compressed image, multi-page PDF | 20 |
| Currency | USD, ZWG (ZiG), ZAR | 30 |
| Language on the document | English, Shona, isiNdebele | 20 (whatever exists) |
| Capture quality | sharp, blurred, glare, low light, cropped, rotated | 15 |
| Phone class (photos and selfies) | budget Android, mid Android, iPhone | 30 |
| Outcome | matched and confirmed, never paid, duplicate, confirmed fake | all available |

For faces, also track skin tone (Monk scale bands), age band, glasses and head coverings, and
lighting. Every group needs **at least 30 genuine pairs** before its false-reject rate is reported.
A group below that is reported as "not measured", and the face detector may not escalate on it.

## 3. Where the data comes from

### 3.1 Historical backlog (fastest, highest value): weeks 2–6

Finance already holds past proofs of payment and the matching bank statements. A proof matched to
a statement line has a **label for free**: the statement says what the receipt should read.

1. Pull 6–12 months of proofs (from email, WhatsApp and the finance shared drive) and the
   statements for the same accounts and months.
2. Upload them through the console, so each one goes through the normal pipeline, and import the
   statements.
3. Claims that match a credit are labelled automatically. Export them with
   `python scripts/export_labelled_set.py <dir>`.
4. Finance clerks check the unmatched ones in the review console. Every correction they make is
   stored and exported by `scripts/export_corrections.py`.

**Target:** 1,000+ proofs, of which 300+ are matched and labelled.

### 3.2 Shadow pilot (ongoing, from week 6)

Run the live intake with `POPS_SHADOW_MODE_ENABLED=true` and the detectors at
`POPS_DETECT_MODE=shadow`. Every reviewer decision, correction and fraud resolution becomes a label:

- reviewer field corrections → reader training pairs (#1, #2);
- `confirmed_fake` and `false_positive` → detector and risk-scorer labels (#5, #10), via
  `python -m training.detect.export_confirmed`;
- duplicate holds resolved by staff → near-duplicate pairs (#4).

**Target:** about 50 labelled claims per working day per organisation.

### 3.3 Recapture sessions (weeks 4–8): for near-duplicates and robustness

Take 200 genuine backlog proofs and recreate how fraudsters reuse them: screenshot of a screenshot,
a photo of the screen at an angle, crop, WhatsApp forward, print and re-photograph, PDF to image.
Label every copy with its source proof. These are the positives for #4 and the evasion split for
#5.

### 3.4 Red-team fakes (weeks 6–10): for the forgery detectors

Staff volunteers, under a written brief, make fakes the way fraudsters do: edit amounts and dates
in phone photo editors, Canva and PDF editors; retype receipts in Word; generate receipts with
image models; and alter genuine receipts with AI inpainting. Record the tool and method for every
fake, so results can be reported per generator.

**Target:** 300+ receipt fakes across at least 6 methods, and 100+ ID fakes. They are kept
labelled as red-team fakes: they show how well the detector catches *those methods*, not real-world
fraud.

### 3.5 KYC volunteers (weeks 6–12): for the face and ID models

Run a consented session with staff, students and partner volunteers:
- an ID photo and 3 selfies each, on their own phones, in normal and poor light;
- attack captures of the same people: a selfie replayed on another screen, a printed photo, and a
  face-swapped image.

Volunteer images are deleted when the study ends (state the date in the consent form).

**Target:** 300+ people, which gives 300+ genuine pairs and 3,000+ impostor pairs once re-paired.

### 3.6 Synthetic data (any time, never for accuracy claims)

- `scripts/generate_mock_pops.py` gives 500 watermarked synthetic receipts. Use them to test that a
  trainer works.
- `training/detect/synth.py` makes synthetic forgeries from genuine pictures.

Synthetic data trains the pipeline and pads rare classes. It is **never** used to report
real-world accuracy.

### 3.7 Public datasets (only after licence approval)

Deepfake, presentation-attack and document-forgery sets (for example SIDTD) are for **evaluation
only** unless the licence clearly allows training and commercial use. Each one is recorded in
`docs/third-party-notices.md` before download. None contains African IDs, so local data stays
essential.

## 4. Labelling protocol

1. **Schema.** Labels use the exact keys of `ReceiptFields` and `IdFields`. Copy values as printed
   (do not reformat); the engine's normalisation decides equality.
2. **Ground truth beats opinion.** When a bank or alert record exists, its amount and reference are
   the label. A clerk labels only fields with no record behind them (date as printed, sender,
   status).
3. **Double-label 10%.** A second clerk labels a random 10% blind. Report agreement per field;
   below 95% on a field means the guideline for it needs fixing.
4. **Edge cases need a written rule**: a smudged digit (mark "unreadable", do not guess); two
   amounts (amount paid, not the balance); fees; a receipt dated in another time zone; a
   screenshot showing several transactions.
5. **Fakes.** Only an admin decision (`confirmed_fake`) or the red-team log makes something "fake".
   A reviewer's suspicion is not a label.
6. **Faces.** "Same person" comes from the volunteer roster, never from the model.
7. **Tool.** Use the review console for reader corrections. Use Label Studio (self-hosted) for
   anything the console cannot label, such as recapture pairs and attack types.

## 5. Splits that keep the numbers honest

| Split | Contents | Rule |
| --- | --- | --- |
| **Frozen benchmark** | 300 real proofs across the coverage grid, plus the 84 existing samples if consented | Never trained on, never changed between model versions |
| **Held-out real set** | 15% of each new batch | Split **by payer and by month**, never by random row (near-identical receipts from one payer leak) |
| **Evasion split** | Recaptured copies from §3.3 | Only for evaluation |
| **Training** | Everything else | Versioned with DVC; each model card names the version it used |

## 6. Storage, access and retention

- Store datasets in a private, encrypted S3-compatible bucket (or `./var/` on the training server),
  never in the repository. Access is limited to the named ML engineer and the data owner, and
  logged.
- Each dataset version has a manifest: file SHA-256, source (backlog, pilot, red team, volunteer,
  synthetic), consent reference, split, and labels.
- Mask personal data the model does not need (account numbers beyond the last 4, phone numbers,
  ID photos for reader-only training) before data leaves the production database.
- Retention: delete volunteer and red-team images at study end. Delete payer data with the claim
  under the normal retention policy. Delete exported training copies when the model card is
  signed, unless the frozen benchmark needs them.
- Training and inference stay on our own machines (see `docs/models.md`). No dataset is sent to an
  outside AI service.

## 7. Roles

| Role | Does |
| --- | --- |
| Data owner (finance lead) | Approves consent, licences and releases; owns the frozen benchmark |
| DPO / legal | Data-protection review, consent wording, retention |
| Finance clerks (2–3) | Backlog upload, corrections, double-labelling |
| Admin reviewers | Fraud decisions (`confirmed_fake` / `false_positive`) |
| Red-team volunteers (3–5) | Make and log fakes |
| KYC study coordinator | Volunteer sessions, roster, deletion |
| Fluent Shona and isiNdebele reviewers | Language rows in the coverage grid; status-word and month lists |
| ML engineer | Exports, splits, training, model cards |

## 8. Timeline and order of training

| Weeks | Collect | Then train or measure |
| --- | --- | --- |
| 0–2 | Governance (§0), move the committed samples | — |
| 2–6 | Backlog (§3.1): 1,000 proofs, statements | **Benchmark** the readers (#1, #2) on the frozen set; fix provider templates and statement profiles |
| 4–8 | Recapture sessions (§3.3) | Near-duplicate embedding (#4); document-type classifier (#3) |
| 6–10 | Red team (§3.4); shadow pilot starts (§3.2) | Receipt forgery detector (#5), classical track, then CNN; **shadow mode** |
| 6–12 | KYC volunteers (§3.5) | Calibrate the face threshold (#8); benchmark the ID reader (#6) |
| 10–16 | Pilot corrections accumulate | Fine-tune the reader (#1) **only if** the benchmark shows a gap; ID forgery (#7) and face attack detectors (#9) in shadow |
| 16+ | 100+ confirmed fakes | Fraud risk scorer (#10); re-measure all detectors against real outcomes before any leaves shadow mode |

Every trained model gets a model card (`docs/model-cards/TEMPLATE.md`), runs in shadow mode first,
and meets the acceptance gates in `authenticity-detectors.md` before it escalates anything.

## 9. Tracking progress

Report weekly, in the project tracker:

- counts per cell of the coverage grid (§2), with gaps highlighted;
- labelled items per model against target (§1);
- double-label agreement per field;
- confirmed fakes and false positives so far;
- reader accuracy and fraud-signal precision from *Replay & accuracy* (`GET /admin/accuracy`).

## 10. Tools that already exist

| Step | Tool |
| --- | --- |
| Labelled reader set from confirmed payments | `backend/scripts/export_labelled_set.py` |
| Reviewer corrections | `backend/scripts/export_corrections.py`, `GET /admin/training/corrections` |
| Reader benchmark and model-card table | `backend/scripts/benchmark_reader.py --card` |
| Fake / not-fake labels | `python -m training.detect.export_confirmed`, `GET /admin/training/detector-labels` |
| Detector dataset, training, evaluation | `training.detect.build_dataset`, `train_linear`, `train_cnn`, `evaluate` |
| Face threshold | `backend/tools/eval/face_eval.py` |
| Tamper check measurement | `backend/tools/eval/tamper_eval.py` |
| Near-duplicate threshold (perceptual hash) | `backend/scripts/calibrate_phash.py` |
| Donut fine-tuning | `scripts/train_extractor.py` |

**Still missing:**
- a recapture-pair export for the near-duplicate model;
- a coverage-grid report;
- a per-claim training opt-in. Today each claim stores only the privacy-notice version the payer
  saw (`consent_version`), and training consent is recorded per organisation.
