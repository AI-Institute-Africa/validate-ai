import { describe, expect, it } from "vitest";
import { DICTS, EN } from "./i18n";
import { FLAGGED_DRAFTS, REVIEWED, REVIEWED_KEYS, coverage, parityProblems } from "./lib/i18nGate";

describe("dictionaries", () => {
  for (const lang of ["sn", "nd"] as const) {
    it(`${lang} has no keys English lacks and keeps every placeholder`, () => {
      const extra = Object.keys(DICTS[lang]).filter((k) => !(k in EN));
      expect(extra).toEqual([]);
      // keys not yet translated fall back to English by design; only placeholder drift is an error
      const problems = parityProblems(EN, DICTS[lang]).filter((p) => p.startsWith("placeholders"));
      expect(problems).toEqual([]);
    });

    it(`${lang}: nothing is signed off that does not exist, and a flagged draft is never live`, () => {
      for (const k of REVIEWED_KEYS[lang]) {
        expect(DICTS[lang][k], `signed-off key ${k} has no text`).toBeDefined();
        expect(FLAGGED_DRAFTS[lang][k], `signed-off key ${k} is also flagged`).toBeUndefined();
      }
      for (const [k, f] of Object.entries(FLAGGED_DRAFTS[lang])) {
        expect(DICTS[lang][k], `flagged draft ${k} is still in the live dictionary`).toBeUndefined();
        expect(DICTS[lang][k] ?? "").not.toBe(f.text);
      }
    });

    it(`${lang} is only switched on as a whole when every string is signed off`, () => {
      const c = coverage(lang, EN, DICTS[lang], REVIEWED_KEYS[lang]);
      if (REVIEWED[lang]) expect(c.live, `${lang} is marked reviewed but ${c.missing.length} strings are missing`).toBe(true);
    });
  }
});
