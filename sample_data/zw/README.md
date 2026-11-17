# Zimbabwe examples

Starting points, not facts. None of these layouts has been checked against a real alert or receipt.

- `alert_templates.example.json`: a merchant-side alert template (set `POPS_ALERT_TEMPLATES_FILE`
  to a file like it). The built-in InnBucks, OneMoney and O'mari alert templates are the same kind
  of guess, modelled on EcoCash wording.
- `provider_templates.example.json`: a receipt template with a transaction-reference pattern
  (`POPS_PROVIDER_TEMPLATES_FILE`).

Before relying on any of them, collect at least 20 real messages or receipts from the provider
(redacted is fine), run them through `parse` / the benchmark script, and replace the pattern.
