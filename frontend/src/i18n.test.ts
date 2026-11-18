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

    it(`${lang} has a draft for every string (nothing falls back to English by accident)`, () => {
      const c = coverage(lang, EN, DICTS[lang], REVIEWED_KEYS[lang]);
      expect(c.missing).toEqual([]);
    });

    it(`${lang}: nothing is signed off that does not exist, and a flagged draft is never live`, () => {
      for (const k of REVIEWED_KEYS[lang]) {
        expect(DICTS[lang][k], `signed-off key ${k} has no text`).toBeDefined();
        // A key can be signed off after a bad draft was replaced; only the old wording stays out.
        const flagged = FLAGGED_DRAFTS[lang][k];
        if (flagged) {
          expect(DICTS[lang][k], `signed-off key ${k} is still the flagged wording`).not.toBe(flagged.text);
        }
      }
      for (const [k, f] of Object.entries(FLAGGED_DRAFTS[lang])) {
        // the old wording stays out; a fresh draft may take its place (still unreviewed)
        expect(DICTS[lang][k] ?? "", `flagged draft ${k} is back in the live dictionary`).not.toBe(f.text);
      }
    });

    it(`${lang} is only switched on as a whole when every string is signed off`, () => {
      const c = coverage(lang, EN, DICTS[lang], REVIEWED_KEYS[lang]);
      if (REVIEWED[lang]) expect(c.live, `${lang} is marked reviewed but ${c.missing.length} strings are missing`).toBe(true);
    });
  }
});
