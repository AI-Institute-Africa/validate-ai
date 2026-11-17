# Private deployment (banks, ministries, councils)

The same containers run inside your own cloud account or data centre, so records stay where policy
requires and no outside service sees a payment or a person.

## What you run

`docker-compose.yml` plus `docker-compose.private.yml`: PostgreSQL, Redis, ClamAV, the API, a worker, the
scheduler (`beat`), the console, MinIO (S3-compatible file storage) and the bundled Ollama reader
(`--profile local-vlm`).

```bash
cp .env.example .env     # then set the values below
docker compose -f docker-compose.yml -f docker-compose.private.yml --profile local-vlm up -d
```

## Settings to make before the first start

| Setting | Why |
| --- | --- |
| `POPS_JWT_SECRET` (32+ characters) | signs sessions; the service refuses to start without it |
| `POPS_DATA_REGION` (for example `ZW-onprem`) | states where the data lives; shown on the Compliance screen and in every audit packet; required in production |
| `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD` | file storage keys; keep them out of source control |
| `POPS_OIDC_*` | sign-in through your identity provider, with `pops_role` and `pops_org` claims; multi-factor is required for finance roles and auditors |
| `POPS_AI_ALLOWED_HOSTS` | leave empty: model calls may reach private hosts only |
| `POPS_DOCS_ENABLED` | the interactive API page is off in production unless you turn it on |

The override already sets production mode, self-hosted storage and the self-hosted reader. The service
will not start if a model URL points outside your network or a hosted AI key is set.

## Outbound traffic

Nothing is sent to an outside AI service. Other outbound calls are the ones you configure: webhooks to
your host system, WhatsApp (if used), email or chat alerts, and the daily RBZ exchange-rate fetch
(`POPS_FX_ENABLED`). Allow only those at your firewall.

## Roles for oversight

Besides payer, reviewer, approver and administrator there is a read-only **auditor** role (`pops_role=auditor`).
An auditor can open a case record, the audit trail, the audit packet and the allocation export, and cannot
submit, decide or change settings. Opening a case and downloading an original file are recorded in the audit
trail with the person's identity.

## Keeping records

Retention is set in the organisation's policy (`evidence_retention_days`, `alert_body_retention_days`,
`kyc_retention_days`): when a window passes, files and raw text are removed and the fingerprints and audit
trail stay. See `docs/breach-response.md` for incidents.

## Before go-live

Have counsel confirm the cross-border rules for your hosting choice, the data-controller licence and the
data-protection officer, and the 24-hour breach-reporting duty; run an independent security review.
