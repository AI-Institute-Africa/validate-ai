# Requirements addendum: trained authenticity detectors

Addendum to the BRD (`docs/Validate-BRD.docx`) and the architecture document
(`docs/Validate-System-Architecture-and-Design.pdf`). Those files are the owner's and are not edited; this page records the new
requirement and where it is designed. Status: **planned**.

## Requirement

The platform shall detect, with models trained and run **entirely on the customer's own server or laptop**, with no outside AI
service or API: AI-generated or forged proofs of payment and ID documents, deepfake or AI-cloned faces and presentation
attacks, and near-duplicate (re-photographed or re-rendered) receipts. Text written by a language model is an optional,
advisory signal.

## Rules it must obey

1. A detector never approves or rejects; a high score only sends a claim to a person, and a clean score never lifts a hold.
2. Detectors start in shadow mode and change nothing until measured quality is signed off against stated gates.
3. A missing or failing model is recorded as skipped; the existing rules keep running.
4. Every score is stored with the model version and file hash, so decisions stay explainable after a model changes.
5. No accuracy figure is quoted without its test set; synthetic-only results are labelled as such.
6. Face detectors are evaluated per group (skin tone, age, lighting, phone class) before they may escalate.
7. Face crops and embeddings are personal data: retention, consent notice, audit and private-deployment rules apply.
8. Training data comes from synthetic fakes, consent-gated reviewer outcomes and public datasets whose licences the owner has
   approved; nothing is uploaded anywhere.

## Where it is designed

[`docs/authenticity-detectors.md`](../authenticity-detectors.md) (design, methods, gates), with changes to `fraud-detection.md`,
`kyc.md`, `models.md`, `training-data.md`, `model-cards/TEMPLATE.md`, `configuration.md`, `auto-approval.md`,
`private-deployment.md`, `third-party-notices.md` and the blueprint.
