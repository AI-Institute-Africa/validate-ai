# Shona and Ndebele: how translations go live

Payers see **English** until a fluent speaker has approved the words. A wrong word in a payment
message can cost someone money or trust, so nothing unreviewed is shown.

## For the reviewer
1. Open `frontend/i18n-review/sn.csv` (Shona) or `nd.csv` (Ndebele).
2. For each row, read `english` and the `current_draft`. Write your wording in `reviewer_translation`
   (or leave the draft) and put `yes` in `approved` only if you would be happy to see it on a
   payment screen. Keep placeholders such as `{pct}` and `{n}` exactly as they are.
3. `status` tells you where a row stands: `missing` (English only), `draft` (written, not yet checked by a
   fluent speaker), `signed-off`, or `flagged` (an earlier draft was found wrong and has no replacement yet).
   When a draft replaces a flagged one, the `note` shows the old wording and why it was wrong.
4. Send the file back.

## For the developer
- `npm run i18n:export` (in `frontend/`) regenerates the sheets.
- Applying approved text: put it in the `SN` / `ND` dictionaries in `src/i18n.tsx` and add its key to
  `REVIEWED_KEYS` in `src/lib/i18nGate.ts`. That string is then shown even while the language is off.
- A language is switched on as a whole (`REVIEWED` in the same file) only when every string is signed
  off. Tests enforce this: a signed-off key must have text, a flagged draft can never be live, and a
  language marked reviewed must be complete.
- Staging can preview drafts with `VITE_ALLOW_UNREVIEWED_TRANSLATIONS=true`. Never in production.

## Where things stand
Every payer-facing string (247) now has a Shona and a Ndebele draft, written in plain wording. That covers
the payment and ID pages, the sidebar and page chrome, status names, file problems, and the messages the server
sends about a payment (each message has a neutral key, so the screen can translate it without the server
revealing why).
None is signed off, so payers still see English. The admin and reviewer pages stay in English on purpose,
and so do the demo-only parts (sample buttons, the demo banner).

Messages sent outside the console (WhatsApp replies, and the approve / reject / ask-for-more texts) are in
`backend/app/claims/messages.py`, in the same three languages and under the same rule: a WhatsApp payer
texts `shona` or `ndebele` (or `english`) to choose, but they are answered in English until that language is
switched on (`POPS_PAYER_MESSAGE_LANGUAGES_LIVE=["sn"]` once a fluent reviewer has signed the text off) or the
string is added to `REVIEWED`. Staging can preview drafts with `POPS_ALLOW_DRAFT_PAYER_MESSAGES=true`; production
refuses to start with it. The reason sentences are the same words as the console's (a test keeps them in step).
Still English only: the header lines of the downloadable summary file and anything a reviewer types by hand.
To preview the drafts on a test site: set `VITE_ALLOW_UNREVIEWED_TRANSLATIONS=true`, or run
`localStorage.setItem('validate-allow-draft-translations','1')` in the browser and pick the language.

## What was found wrong in the earlier drafts
An automated audit (not a fluent speaker) flagged four earlier drafts: Shona `hero.title` and `form.trust`,
and Ndebele `form.trust` and `result.green.note`. All the earlier drafts were then replaced. The old wording
is kept in `FLAGGED_DRAFTS` so it is not reused. The new drafts were also written without a fluent speaker,
so a person must check them before they go live.
