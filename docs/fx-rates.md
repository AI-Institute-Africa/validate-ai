# Official ZiG / USD rate (Reserve Bank of Zimbabwe)

The engine fetches the RBZ **interbank ASK rate** (ZWG per 1 USD) each working day, stores it with the
PDF as evidence, and uses it to explain claims paid in a different currency from their invoice.
It supplies a number and its proof; it never moves money.

## Where the rate comes from

The RBZ publishes one PDF a day, reached from the
[exchange rates page](https://www.rbz.co.zw/index.php/research/markets/exchange-rates) by year, month and
day. The file name follows the date, for example
`https://www.rbz.co.zw/documents/Exchange_Rates/2026/November/RATES_13_NOVEMBER_2026.pdf`.

The first data row under INTERBANK RATE is USD. Columns: CURRENCY, INDICES (BID, ASK, MID RATE), then in
ZWG BID RATE, ASK RATE, MID RATE. For Friday, 13 November 2026 the row is
`USD 1 1 1.0000 25.9214 27.2508 26.5861`, so the ask rate is **27.2508**.

## How it runs

- `POPS_FX_ENABLED=true` turns it on (off by default). A Celery beat entry (`pops.fx_fetch`) runs hourly
  on weekdays during `POPS_FX_FETCH_HOURS` (UTC, default `5-16`) until the day's file is stored.
- It tries the dated link with plain HTTP first. If that fails it opens the page in a browser
  (Playwright, optional extra `backend[fxbrowser]`, not in the default image) and finds the day's link.
- It reads the date at the top of the file and checks it is the day asked for, finds the USD row, checks the
  headings, and takes the ask rate. It checks the rate is positive, ask is not below bid, and the move from
  the previous day is within `POPS_FX_MAX_DAILY_MOVE_PCT` (default 25%).
- A rate is saved append-only (`fx_rates`) with the source link, the file's SHA-256 and a stored copy of the
  PDF. A different file for a day already stored raises an alert. Every attempt is logged (`fx_fetch_log`).
- If the file is missing by the last hour, or the layout is not as expected, administrators get an
  `ops.fx_alert` event. The rate is not used.
- Weekends and holidays carry the last rate forward, up to the policy's `fx_max_rate_age_days` (default 4),
  and the answer says which day it is from.
- An approver can enter a rate by hand with a written reason (`POST /admin/fx/manual`, audited).

## How it is used

- `GET /fx/rates?on=YYYY-MM-DD` (reviewer), `GET /admin/fx/status`, and the console page **Exchange rate**.
- The review page shows the rate and the conversion when a claim's currency differs from its invoice.
- Policy (all off or conservative by default): `fx_cross_currency_enabled`, `fx_tolerance_bps` (default 300),
  `fx_max_rate_age_days`. When enabled, such a claim carries `CROSS_CURRENCY_AT_OFFICIAL_RATE`, and
  `RATE_DEVIATION` if the converted payment is further from the invoice than the tolerance, or
  `NO_OFFICIAL_RATE` when there is no usable rate. The rate used is recorded in the decision snapshot.
- **What does not change:** the currency gate. A ZWG credit never settles a USD invoice automatically, the
  ledger refuses mixed-currency allocation, and auto-approval never crosses currencies.

## Before relying on it

Confirm with the RBZ that automated retrieval is allowed, and keep to one fetch a day plus retries. Run
`backend/tools/fx_live_check.py` against the live site once `www.rbz.co.zw` is reachable from the deployment.
