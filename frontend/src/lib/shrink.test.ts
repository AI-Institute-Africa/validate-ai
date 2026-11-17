import { describe, expect, it } from "vitest";
import { fitWithin, shouldShrink } from "./imageEdit";
import { payerWaitKey } from "../labels";
import { EN } from "../i18n";

describe("fitWithin", () => {
  it("never upscales", () => {
    expect(fitWithin(800, 600)).toEqual({ width: 800, height: 600, scaled: false });
  });
  it("keeps the aspect ratio when shrinking", () => {
    expect(fitWithin(4000, 3000)).toEqual({ width: 2000, height: 1500, scaled: true });
    expect(fitWithin(3000, 6000)).toEqual({ width: 1000, height: 2000, scaled: true });
  });
  it("never produces a zero side", () => {
    expect(fitWithin(100000, 1).height).toBe(1);
  });
});

describe("shouldShrink", () => {
  it("only large photos", () => {
    expect(shouldShrink({ type: "image/jpeg", size: 5_000_000 })).toBe(true);
    expect(shouldShrink({ type: "image/jpeg", size: 200_000 })).toBe(false);
    expect(shouldShrink({ type: "application/pdf", size: 9_000_000 })).toBe(false);
    expect(shouldShrink({ type: "image/heic", size: 9_000_000 })).toBe(false);
  });
});

describe("payerWaitKey", () => {
  it("is calm and never hints at suspicion", () => {
    for (const s of ["PENDING_REVIEW", "DUPLICATE_HOLD", "AWAITING_FINANCIAL_CONFIRMATION"]) {
      const key = payerWaitKey(s);
      expect(key).toBeTruthy();
      expect(EN[key!].toLowerCase()).not.toMatch(/fake|fraud|suspic|duplicate|edited|tamper/);
    }
    expect(payerWaitKey("APPROVED")).toBeNull();
  });
});
