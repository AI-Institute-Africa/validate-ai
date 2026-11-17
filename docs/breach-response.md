# Personal-data incidents and the 24-hour clock

The BRD says a personal-data breach must be reported within 24 hours of detection (to be confirmed with
Zimbabwean counsel). The Compliance screen (admin) keeps a register so the clock is never kept in someone's head.

## When something happens

1. **Record it at once** (Compliance, "Record an incident", or `POST /admin/incidents`): kind (breach,
   near miss, other), a short title, what happened, when it was detected (default: now), and the time window
   of the records that may be affected. The report is due 24 hours after detection.
2. **Contain it.** Rotate keys (`POST /alerts/sources/{id}/rotate-key`, `POPS_JWT_SECRET`, storage keys),
   switch off the affected source, or use the kill switches. Everything you do is in the audit trail.
3. **List who may be affected.** `GET /admin/incidents/{id}/affected.csv` lists the claims and ID checks created in
   the incident's window. It is a starting list; a person decides who was really affected.
4. **Report it** to the regulator and record the regulator's reference (`POST /admin/incidents/{id}/reported`).
   The register notes whether the report was late.
5. **Close it** with a note on what was fixed (`POST /admin/incidents/{id}/close`).

## Reminders

While an incident is open and unreported, admins get an `ops.incident_due` message through the usual admin
channels (webhook and email) at 12 hours, at 20 hours, and once the 24 hours have passed. Each stage is sent once.

## Practise it

Run a drill each quarter: record a test incident of kind "near miss", export the affected list, and confirm the
reminders reach the right people.
