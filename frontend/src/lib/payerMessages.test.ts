import { describe, expect, it } from "vitest";
import { DICTS, EN } from "../i18n";
import { payerMessages } from "../labels";

const tIn = (lang: "en" | "sn" | "nd") => (k: string) => DICTS[lang][k] ?? EN[k] ?? k;

describe("payerMessages", () => {
  const claim = { messages: ["Server English one.", "Server English two."], message_keys: ["AWAITING_CREDIT", "SOMETHING_NEW"] };

  it("translates a known key and keeps the server's English for an unknown one", () => {
    const sn = payerMessages(claim, tIn("sn"));
    expect(sn[0]).toBe(DICTS.sn["msg.AWAITING_CREDIT"]);
    expect(sn[0]).not.toBe(EN["msg.AWAITING_CREDIT"]);
    expect(sn[1]).toBe("Server English two.");
  });
  it("English reads exactly what the server wrote for a known key", () => {
    expect(payerMessages({ messages: [EN["msg.AWAITING_CREDIT"]], message_keys: ["AWAITING_CREDIT"] }, tIn("en"))).toEqual([EN["msg.AWAITING_CREDIT"]]);
  });
  it("falls back to the server text when the server sends no keys (older server)", () => {
    expect(payerMessages({ messages: ["Hello"] }, tIn("nd"))).toEqual(["Hello"]);
  });
  it("fills the access end time into the provisional note", () => {
    const out = payerMessages({ messages: ["x"], message_keys: ["PROVISIONAL"], provisional_until: "2026-11-20T10:30:00Z" }, tIn("nd"));
    expect(out[0]).toContain("2026-11-20 10:30");
    expect(out[0]).not.toContain("{until}");
  });
  it("no message key hints at suspicion in any language", () => {
    for (const lang of ["en", "sn", "nd"] as const) {
      for (const [k, v] of Object.entries(DICTS[lang])) {
        if (k.startsWith("msg.")) expect(k).not.toMatch(/FAKE|FRAUD|SUSPECT|FORG/);
        if (k === "msg.MANUAL_CHECK") expect(v.toLowerCase()).not.toMatch(/fake|fraud|suspect/);
      }
    }
  });
});
