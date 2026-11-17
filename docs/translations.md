# Shona and Ndebele: how translations go live

Payers see **English** until a fluent speaker has approved the words. A wrong word in a payment
message can cost someone money or trust, so nothing unreviewed is shown.

## For the reviewer
1. Open `frontend/i18n-review/sn.csv` (Shona) or `nd.csv` (Ndebele).
2. For each row, read `english` and the `current_draft`. Write your wording in `reviewer_translation`
   (or leave the draft) and put `yes` in `approved` only if you would be happy to see it on a
   payment screen. Keep placeholders such as `{pct}` and `{n}` exactly as they are.
3. `status` tells you where a row stands: `missing` (English only), `draft`, `signed-off`, or `flagged`
   (an earlier draft was found wrong; the note says why: do not reuse it).
4. Send the file back.

## For the developer
- `npm run i18n:export` (in `frontend/`) regenerates the sheets.
- Applying approved text: put it in the `SN` / `ND` dictionaries in `src/i18n.tsx` and add its key to
  `REVIEWED_KEYS` in `src/lib/i18nGate.ts`. That string is then shown even while the language is off.
- A language is switched on as a whole (`REVIEWED` in the same file) only when every string is signed
  off. Tests enforce this: a signed-off key must have text, a flagged draft can never be live, and a
  language marked reviewed must be complete.
- Staging can preview drafts with `VITE_ALLOW_UNREVIEWED_TRANSLATIONS=true`. Never in production.

## What was found wrong in the current drafts
An automated audit (not a fluent speaker) flagged four drafts: Shona `hero.title` and `form.trust`, and
Ndebele `form.trust` and `result.green.note`. They were removed from the live dictionaries so English
shows, and kept in `FLAGGED_DRAFTS` for the reviewer. The audit could be wrong; a person decides. Many
other Shona drafts reuse the same verb for "verify", so treat all drafts as unreviewed.
