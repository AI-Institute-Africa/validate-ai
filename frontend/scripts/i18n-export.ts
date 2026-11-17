// Writes one review sheet per language for a fluent reviewer.
//   npm run i18n:export        ->  i18n-review/sn.csv, i18n-review/nd.csv
// Columns: key, english, current_draft, status, note, reviewer_translation, approved (yes/no).
// status: missing (English only so far), draft (not signed off), signed-off, flagged (do not reuse).

import { mkdirSync, writeFileSync } from "node:fs";
import { DICTS, EN } from "../src/i18n";
import { FLAGGED_DRAFTS, REVIEWED_KEYS, coverage, type Lang } from "../src/lib/i18nGate";

const csv = (cells: string[]) => cells.map((c) => `"${c.replace(/"/g, '""')}"`).join(",");

mkdirSync("i18n-review", { recursive: true });
for (const lang of ["sn", "nd"] as Lang[]) {
  const rows = [csv(["key", "english", "current_draft", "status", "note", "reviewer_translation", "approved"])];
  for (const key of Object.keys(EN)) {
    const draft = DICTS[lang][key];
    const flagged = FLAGGED_DRAFTS[lang][key];
    const status = flagged ? "flagged" : draft === undefined ? "missing" : REVIEWED_KEYS[lang].has(key) ? "signed-off" : "draft";
    rows.push(csv([key, EN[key], draft ?? flagged?.text ?? "", status, flagged?.why ?? "", "", ""]));
  }
  writeFileSync(`i18n-review/${lang}.csv`, rows.join("\n") + "\n");
  const c = coverage(lang, EN, DICTS[lang], REVIEWED_KEYS[lang]);
  console.log(`${lang}: ${c.total} strings, ${c.translated} drafted, ${c.reviewed} signed off, ${c.missing.length} missing`);
}
