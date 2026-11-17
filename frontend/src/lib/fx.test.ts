import { describe, expect, it } from "vitest";
import { convertMinor, gapBps, isCrossCurrency, normaliseCurrency } from "./fx";

describe("official rate helpers", () => {
  it("converts at the ask rate both ways, matching the server", () => {
    expect(convertMinor(10000, "USD", "ZWG", 27.2508)).toBe(272508);
    expect(convertMinor(272508, "ZWG", "USD", 27.2508)).toBe(10000);
    expect(convertMinor(500, "USD", "USD", 27.2508)).toBe(500);
  });
  it("rejects a non-positive rate", () => expect(() => convertMinor(1, "USD", "ZWG", 0)).toThrow());
  it("treats ZiG and ZWL as ZWG", () => {
    expect(normaliseCurrency("zig")).toBe("ZWG");
    expect(normaliseCurrency("ZWL")).toBe("ZWG");
  });
  it("detects a cross-currency pair only inside the official pair", () => {
    expect(isCrossCurrency("ZWG", "USD")).toBe(true);
    expect(isCrossCurrency("USD", "USD")).toBe(false);
    expect(isCrossCurrency("ZAR", "USD")).toBe(false);
    expect(isCrossCurrency(null, "USD")).toBe(false);
  });
  it("measures the gap in basis points", () => {
    expect(gapBps(9000, 10000)).toBe(1000);
    expect(gapBps(10000, 10000)).toBe(0);
  });
});
