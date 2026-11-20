# Mobile view plan

**Status: agreed; Phases 0–3 complete.** Minimum supported width is **375 px**, **every page** is
in scope (payer and staff), and an installable PWA / service worker is **out of scope**. The
`frontend/e2e/mobile.py` gate passes on all 20 routed pages at 375 px and 768 px with a touch
context, checking overflow, touch targets, visible titles and layout shift. It then drives a sample
payment through submit → result → track, checks the ID camera inputs, verifies offline submit →
online retry (including from a backgrounded tab), and triages a claim on a phone. Staff tables become
cards through one shared helper, and a bundle budget keeps the route split from regressing.
It follows the existing design tokens
in [`frontend/src/tokens.css`](../frontend/src/tokens.css) and the contrast rules in
[`docs/brand/colours.md`](brand/colours.md); it does not propose a new visual language.

## Why this plan looks the way it does

Payers meet Validate on a phone: they photograph a receipt, check where their claim is, and
sometimes retry a failed upload on a poor connection. Finance staff meet it on a desk, but still
need to triage a queue from a phone or tablet when a claim is blocking someone.

So the priority is **not** desktop parity on every screen:

1. **Payer journeys must be complete on a 375 px phone**, one-handed, on a slow connection.
2. **Staff must be able to triage and decide** from a phone, with the evidence readable; dense
   policy editing may remain tablet/desktop-best but must never be a dead end.
3. No page-level horizontal scrolling. Wide tables either become cards or scroll inside a clearly
   labelled region with a sticky first column.
4. Touch and accessibility are part of "done": 44 px targets, no iOS focus zoom, safe areas, 200 %
   zoom, visible focus, reduced motion.

## What already works (do not rebuild it)

Found in the current frontend; the plan extends these rather than replacing them.

| Already present | Where |
| --- | --- |
| Proper viewport meta, lazy-loaded routes so a payer never downloads the admin console | `frontend/index.html:5`, `frontend/src/main.tsx:21-37` |
| `100dvh` shell for collapsing mobile browser toolbars | `frontend/src/polish.css:14,25` |
| Off-canvas drawer + scrim below 960 px, closes on route change | `frontend/src/main.tsx:202-204,225-249`, `frontend/src/ui.css:60-68` |
| Single-column splits at 900 px; grids at 640/900 px | `frontend/src/styles.css:115-118,449-450`, `frontend/src/ui.css:142-143` |
| Card-as-table pattern (now a shared `CardTable` used by every reviewer/admin table) | `frontend/src/components/CardTable.tsx`, `frontend/src/components/cardTable.css` |
| Camera capture on payment proofs and Image to text; photo downscaling | `frontend/src/pages/Scan.tsx:702-707`, `frontend/src/pages/ImageToText.tsx:299`, `frontend/src/lib/imageEdit.ts:54-94` |
| Offline outbox with automatic retry on `online` | `frontend/src/lib/useClaimSender.ts`, `frontend/src/lib/outbox.ts` |
| Payer-specific small-screen rules: stepper, capture row, 3-column tracking timeline | `frontend/src/pages/scan.css:71-84`, `frontend/src/pages/track.css:21` |
| Reduced motion everywhere; pointer spotlight/tilt skipped on touch | `frontend/src/ui.css:11`, `frontend/src/motion.css:265`, `frontend/src/lib/flair.ts:9-14` |
| Focus-managed `Dialog` and `Menu` components | `frontend/src/components/Dialog.tsx`, `frontend/src/components/Menu.tsx` |

## Targets and breakpoints

Keep the existing breakpoints; the minimum supported width is 375 px. No new design is needed.

| Width | Target | Layout rules |
| --- | --- | --- |
| 375–560 px | Phone (iPhone SE and up, low-end Android) | One column; drawer nav; card tables; 44 px targets; CTA full width; safe-area padding; labels above fields |
| 561–720 px | Large phone / small tablet landscape | One column for forms; two columns only for short fact lists and thumbnails; card tables |
| 721–960 px | Tablet portrait (iPad, 768 px) | Drawer nav; two-column grids where content is short; viewer stops being sticky at ≤900 px |
| ≥961 px | Desktop | Sidebar as today; tables as tables; hover shortcuts available |

Portrait is the primary phone orientation; landscape must not clip sticky bars or the viewer.
Test at 375 × 812 and 768 × 1024; 375 px is the floor, not a best case.

## Workstream A — shell and foundations (do first)

These are cross-cutting fixes. Every later page work assumes them.

| # | Change | Files | Done when |
| --- | --- | --- | --- |
| A1 | Add `viewport-fit=cover`; define `--safe-top/--safe-bottom/--safe-left/--safe-right` from `env(safe-area-inset-*)` and apply to the demo bar, topbar, page padding, footer, drawer, persona menu, modals and sticky bottom bars. | `frontend/index.html:5`, `frontend/src/tokens.css`, `frontend/src/ui.css`, `frontend/src/styles.css` | Nothing is hidden by the notch or home indicator on a notched device; portrait and landscape both checked. |
| A2 | One authoritative touch-target rule **after** the current overrides: all buttons, links acting as buttons, selects and tab controls ≥44 px under `(pointer: coarse)`. Fix the current 38/36/32/30 px cases (`.btn`, `.rv-pill`, `.rv-topbar a`, icon-only edit buttons, `.rv-tab`, `.seg button`, `.lang-switch`, `.icon-btn`). | `frontend/src/polish.css:59-60`, `frontend/src/pages/review.css:20-26,31,60,183`, `frontend/src/pages/scan.css:24`, `frontend/src/ui.css:210`, `frontend/src/styles.css:396-407`; new `frontend/src/mobile.css` imported last | Verified with a Playwright assertion, not by eye. Check cascade in both `npm run dev` and built output: lazy page CSS can load after shell CSS. |
| A3 | Set `font-size: 16px` on all text inputs, selects and textareas under `(pointer: coarse)` so iOS Safari does not zoom on focus. | `frontend/src/mobile.css` (reviewer pages already do this at `review.css:23`) | No viewport change when focusing a field on iOS. |
| A4 | Make the mobile drawer accessible: `aria-expanded`/`aria-controls` on the menu button, move focus in, trap it, close on Escape, restore focus to the button, lock background scroll and mark background inert/`aria-hidden`. Replace the native `window.confirm` for demo reset with `Dialog`. | `frontend/src/main.tsx:139-152,202-211,225-256`, `frontend/src/components/Dialog.tsx` | Keyboard and screen-reader check passes; matches the behaviour of `Menu.tsx` and `PersonaMenu`. |
| A5 | Publish a z-index map (scrim 40, drawer 50, toasts 100, dialog 200). Close the drawer before opening a dialog, or raise dialogs above it. Move toasts above sticky bottom bars on phones and add safe-area padding. | `frontend/src/ui.css:49,59,62-65,150-151,272`, `frontend/src/styles.css:324-333`, `frontend/src/pages/review.css:195` | Toasts never cover the confirm/undo action; dialog is always on top. |
| A6 | Give tap equivalents to hover-only affordances under `@media (hover: none)`: keep visible borders/labels instead of relying on `:hover`, and make touch feedback immediate. Cap decorative transforms so they do not stick after a tap. | `frontend/src/motion.css:68-118,239-250`, `frontend/src/styles.css:141` | Every hover hint has a non-hover equivalent; no stuck tilt/highlight after tapping. |
| A7 | Global overflow guardrails: `min-width: 0` on grid/flex children, `overflow-wrap: anywhere` on `.data`, `.mono`, `.rv-code`, `.reason-code`, `code.key`, hashes and long references; remove `.rv-why { min-width: 220px }` on phones. | `frontend/src/ui.css:117,121,135`, `frontend/src/pages/review.css:15,180`, `frontend/src/styles.css:446` | Automated "no horizontal scroll" assertion passes on all routes at 375 px. |

## Workstream B — payer journeys (highest user value)

| # | Change | Files | Done when |
| --- | --- | --- | --- |
| B1 | **Verify a payment:** keep the camera path; make stepper labels survive 375 px (number + short label, no truncation), full-width primary submit, wrapped file rows with ≥44 px edit/remove buttons, readable upload progress and offline outbox, bottom padding for the home indicator. | `frontend/src/pages/Scan.tsx`, `frontend/src/pages/scan.css`, `frontend/src/lib/useClaimSender.ts` | A sample claim can be submitted, tracked and retried offline on a 375 px touch context. |
| B2 | **Verify an ID:** add `capture="environment"` for the document and `capture="user"` for the selfie; replace the `div[role="button"]` drop zone containing a nested remove button with a real `<label>`/`<button>` structure; stack the document/selfie comparison on phones; keep the "Try a sample" chips tappable. | `frontend/src/pages/Kyc.tsx:37-58`, `frontend/src/ui.css:226-244` | Camera opens directly; no nested interactive controls; both previews visible without horizontal scroll. |
| B3 | **Track a claim:** check the 3-column timeline at 375 px (wordy states wrap), keep the next-step panel and copy-code action within thumb reach, ensure status stamps are readable in both themes. | `frontend/src/pages/Track.tsx`, `frontend/src/pages/track.css:1-21`, `frontend/src/components/ProvisionalBanner.tsx` | Status and next action understood without zooming; no clipped step labels. |
| B4 | **Home / guided tour:** horizontal step strip uses scroll snap and a visible current step at phone width; case files stack cleanly; hero CTA is full width; demo banner wraps without covering content. | `frontend/src/pages/Home.tsx`, `frontend/src/ui.css:155-223`, `frontend/src/main.tsx:217-224` | All six stories can be followed on a phone; current step always visible. |
| B5 | **Image to text:** camera capture stays; wrap long extracted text, add a tappable Copy action, keep file info and reader errors readable at 375 px. | `frontend/src/pages/ImageToText.tsx`, `frontend/src/pages/scan.css` | Full extracted text readable with no sideways scroll. |
| B6 | **Orientation / context:** at ≤560 px the topbar hides the crumb and persona label. Keep a compact page title in topbar or rely on the page heading; verify no page loses its identity. | `frontend/src/ui.css:247-252`, `frontend/src/main.tsx:251-256` | Every page has a visible title on a phone. |

Phase 1 is implemented across `Scan`, `Kyc`, `Track`, `Home` and `ImageToText`. The stepper no longer
truncates at 375 px, file actions wrap with 44 px targets, the ID page uses real labels with the
correct camera hints and a stacked preview, Track has a tappable copy-code action, the tour strip
scroll-snaps to the current story, extracted text wraps without sideways scroll, and the topbar
keeps a compact page title. `mobile.py` now covers the whole payer journey, including the existing
submit-and-retry outbox.

## Workstream C — staff console on small screens

| # | Change | Files | Done when |
| --- | --- | --- | --- |
| C1 | Apply the existing `rv-cards` treatment to the other reviewer/admin tables: credits, obligations, alerts, ID checks, auto-approved, insights tabs (exposure/scorecard/replay/FX/compliance) and bulk. Add `data-label` to cells; factor the row pattern into a small shared helper/component rather than copying CSS again. | `frontend/src/pages/review.css:221-236`, `frontend/src/pages/{Credits,Obligations,Alerts,KycReview,AutoApproved,Insights,Bulk,QueueBulk}.tsx` and the tab pages rendered by `Insights.tsx` | No table requires sideways page scroll at 375 px; keyboard-less users can still select, enter a last-4 and confirm. |
| C2 | Image viewer: replace `title`-only explanations of proof boxes with a tappable annotation list or disclosure; either allow taps on boxes or provide an equivalent "highlight this field" control. Add pinch/pan-friendly zoom and keep the image inside the viewport. | `frontend/src/pages/ClaimReview.tsx:120-140`, `frontend/src/styles.css:451-457`, `frontend/src/pages/review.css:89-95,189-194` | A reviewer can identify and explain a flagged region by touch alone. |
| C3 | Decision bar: safe-area padding, wrap actions without covering content, keep the primary action visible, and reposition toasts so they cannot cover Confirm/Undo. Check with the on-screen keyboard open. | `frontend/src/pages/review.css:195-198,213-218`, `frontend/src/styles.css:324-333` | Reviewer can confirm a claim on a 375 px phone without scrolling past an overlay. |
| C4 | Touch alternatives to keyboard shortcuts and native dialogs: visible action buttons are already present in queue/claim review; extend the same pattern to the remaining `window.prompt`/`window.confirm` sites using `Dialog`. | `frontend/src/pages/Queue.tsx:122-156`, `frontend/src/pages/ClaimReview.tsx:447-457`, `frontend/src/components/ShortcutLegend.tsx`, native prompt sites in `KycReview.tsx`, `Guardrails.tsx`, `Compliance.tsx`, `AutoApproved.tsx`, `Alerts.tsx` | No flow requires a hardware keyboard or an OS-native prompt. |
| C5 | Insights charts and CSV/export controls: confirm they remain legible on 768 px, wrap controls instead of clipping, and keep labels with values when tables become cards. | `frontend/src/pages/Insights.tsx`, `frontend/src/pages/Scorecard.tsx`, `frontend/src/pages/Replay.tsx`, `frontend/src/pages/Compliance.tsx`, `frontend/src/pages/Fx.tsx`, `frontend/src/pages/Exposure.tsx` | No clipped chart legend or export action at 768 px. |

Phase 2 is implemented. `CardTable`/`CardCell` convert all 24 reviewer/admin tables (the payer
case-file table on Home stays a table). Claim review has a tappable proof legend and “Show on
image” buttons with hover kept as an enhancement; the decision bar keeps its primary action in
thumb reach with safe-area padding. All seven `window.prompt`/`window.confirm` sites now use the
shared `ConfirmDialog`/`ReasonDialog`, and the 721–900 px rules keep tabs, chips, code and tiles
inside a 768 px viewport. `mobile.py` now covers the staff journey: a reviewer opens a queued
claim, exercises the touch annotation control, focuses the last-4 from the decision bar and
confirms it at 375 px, then checks evidence and overflow at 768 px.

## Workstream D — performance and resilience on phones — **complete**

- Route-level code splitting is kept by `npm run budget` (`frontend/scripts/bundleBudget.mjs`), which
  runs after `npm run build` in CI. It caps the initial JS/CSS and the largest lazy route chunk, so
  staff pages cannot creep into the payer shell unnoticed.
- Proof thumbnails use `loading="lazy"`; the claim viewer reserves the proof's real dimensions from
  evidence metadata, and ID thumbnails reserve their height. Photo downscaling in
  `frontend/src/lib/imageEdit.ts` is unchanged. `mobile.py` asserts cumulative layout shift stays
  below 0.1 on every route.
- The outbox remains legible at phone width. Returning to a backgrounded tab now retries a waiting
  upload (the online event can be missed on phones), with the existing Idempotency-Key preventing
  duplicate claims. `mobile.py` drives that exact backgrounded-tab journey.
- **Out of scope:** no service worker, manifest or installable PWA. The existing outbox covers
  submit-and-retry; offline shell caching of sensitive evidence would need a separate review.
- Verified targets: no page-level horizontal overflow at 375/768 px, 44 px touch targets, no visible
  layout shift from images, and the payer landing title plus primary action visible without scrolling.
  INP is not measured by this gate; keep interaction responsive by reviewing the manual checklist.

## Workstream E — test and CI — **complete**

`frontend/e2e/mobile_asserts.py` is the shared source of truth for `assert_no_horizontal_scroll`,
`assert_touch_targets`, `assert_visible_title` and the layout-shift check. `mobile.py` runs all of
them on every routed page at both 375 px and 768 px with `is_mobile=True, has_touch=True` and a real
device scale factor, then drives the payer and staff journeys. `run_demo_suite.sh` includes
`mobile.py`, and `.github/workflows/ci.yml` runs that suite in the `browser` job, so the gate blocks
merges. `frontend/src/lib/focusTrap.test.tsx` covers drawer focus management with Vitest and
Testing Library. `visual_snapshots.py` remains a documented manual before/after tool; it is not a
pass/fail gate.

### Manual checklist (about 10 minutes)

Run a story or two in the demo, then check on a real phone if one is available:

- [ ] **Notch and landscape:** safe areas keep the title and actions clear; no content hides under
      the browser chrome at 375 × 812 and in landscape.
- [ ] **iOS focus zoom:** tapping an input does not zoom the page (inputs are at least 16 px).
- [ ] **One-handed reach:** the drawer trigger and primary actions are reachable with a thumb.
- [ ] **Dark mode:** text, chips and proof boxes stay legible against the dark panels.
- [ ] **200 % text size:** titles, buttons and card labels wrap without clipping or overlap.
- [ ] **Reduced motion:** the drawer, tooltips and transitions do not animate when the OS asks for
      reduced motion.

## Delivery order

| Phase | Scope | Exit gate |
| --- | --- | --- |
| 0 — Foundations (Workstream A) — **complete** | Safe areas, touch targets, input zoom, drawer a11y, overflow guardrails, `e2e/mobile.py` gate | **Passing:** `mobile: ok (20 pages at 375px)`; drawer a11y test passes |
| 1 — Payer flows (B) — **complete** | Verify, ID, track, home/tour, image-to-text | **Passing:** `mobile: ok (20 pages at 375px; payment, track, ID and offline retry)` |
| 2 — Staff triage (C) — **complete** | Card tables, viewer annotations, decision bar, native dialogs | **Passing:** `mobile: ok (... staff triage; 768px evidence)`; full demo suite green |
| 3 — Polish and guardrails (D, E) — **complete** | Bundle budget, lazy images, shared mobile assertions, backgrounded retry, manual checklist | **Passing:** `mobile: ok (20 pages at 375px and 768px; payment, track, ID, offline and backgrounded retry, staff triage)`; `npm run budget` green in CI |

Phases 0–1 were small, self-contained changes to shared CSS plus one new e2e file. Phase 2 was the
largest because it touched many pages, and was built on the shared card-table helper it introduced.
Phase 3 added the guardrails: the same layout assertions run on every route at both widths, and a
small bundle budget protects the route split.

## Agreed decisions

1. **Support floor:** 375 px. Smaller widths are not a target.
2. **Scope:** every page, including the staff console on phones and tablets.
3. **PWA/offline shell:** ignored for this work. Keep the existing submit-and-retry outbox only.
4. **Implementation:** Phases 0–3 complete; the mobile view is done.
