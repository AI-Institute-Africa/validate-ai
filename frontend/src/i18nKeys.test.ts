import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { DICTS, EN } from "./i18n";

// Every translation key used on a payer-facing screen must exist in English (and so, by the dictionary
// tests, in Shona and Ndebele). Catches typos and keys that were never added.
const PAYER_FILES = ["src/main.tsx", "src/pages/Scan.tsx", "src/pages/Kyc.tsx", "src/pages/Track.tsx", "src/ui.tsx", "src/labels.ts"];

describe("translation keys used on payer screens", () => {
  for (const file of PAYER_FILES) {
    it(`${file} only uses keys that exist`, () => {
      const src = readFileSync(file, "utf8");
      const keys = [...src.matchAll(/\bt\(\s*"([A-Za-z0-9._]+)"\s*\)/g)].map((m) => m[1]);
      const missing = [...new Set(keys)].filter((k) => !(k in EN));
      expect(missing).toEqual([]);
    });
  }

  it("dynamic key families are complete", () => {
    for (const state of ["RECEIVED", "PROCESSING", "NEEDS_INFORMATION", "DOCUMENT_VERIFIED", "AWAITING_FINANCIAL_CONFIRMATION", "FINANCIALLY_CONFIRMED", "PARTIALLY_ALLOCATED", "PENDING_REVIEW", "APPROVED", "REJECTED", "DUPLICATE_HOLD", "REVERSED_OR_REFUNDED", "SUBMITTED", "NEEDS_REVIEW", "VERIFIED", "EXPIRED"]) {
      expect(EN[`state.${state}`], state).toBeDefined();
    }
    for (const s of ["VERIFIED", "NEEDS_REVIEW", "NEEDS_INFORMATION", "REJECTED"]) expect(EN[`kyc.next.${s}`], s).toBeDefined();
    for (const e of ["top", "right", "bottom", "left"]) expect(EN[`crop.${e}`], e).toBeDefined();
  });

  it("Shona and Ndebele never reuse the English sentence by accident", () => {
    const sameAllowed = new Set(["nav.scan", "capture.scan", "kyc.selfie.label"]); // loan words that read the same
    for (const lang of ["sn", "nd"] as const) {
      const same = Object.keys(EN).filter((k) => DICTS[lang][k] === EN[k] && !sameAllowed.has(k) && EN[k].length > 12);
      expect(same, `${lang} still has English text for: ${same.join(", ")}`).toEqual([]);
    }
  });
});
