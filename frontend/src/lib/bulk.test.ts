import { describe, expect, it } from "vitest";
import type { Candidate, ReviewDetail } from "../api";
import { approvable, last4Ready, pruneSelection, runSequentially, summarise, toggle, toggleAll } from "./bulk";

const cand = (id: string, passed = true) => ({ credit: { credit_id: id }, passed }) as unknown as Candidate;
const detail = (over: Record<string, unknown> = {}, candidates: Candidate[] = [cand("cr1")]): ReviewDetail =>
  ({
    claim: { state: "PENDING_REVIEW", approval_tier: "GREEN", risk_level: "low", reason_codes: [], candidate_credit_id: "cr1", ...over },
    candidates,
  }) as unknown as ReviewDetail;

describe("approvable", () => {
  it("accepts a green, matched, unflagged claim", () => {
    const r = approvable(detail());
    expect(r.ok).toBe(true);
  });
  it("refuses anything that is not clearly safe, and says why", () => {
    const cases: [Record<string, unknown>, RegExp][] = [
      [{ state: "REJECTED" }, /Not waiting/],
      [{ state: "DUPLICATE_HOLD" }, /Not waiting/],
      [{ approval_tier: "AMBER" }, /Not green/],
      [{ approval_tier: null }, /Not green/],
      [{ risk_level: "high" }, /fraud risk/],
      [{ reason_codes: ["TAMPER_SUSPECTED"] }, /Flagged/],
      [{ reason_codes: ["SUSPECTED_FAKE"] }, /Flagged/],
    ];
    for (const [over, why] of cases) {
      const r = approvable(detail(over));
      expect(r.ok).toBe(false);
      if (!r.ok) expect(r.why).toMatch(why);
    }
  });
  it("needs the matched credit to pass every gate", () => {
    expect(approvable(detail({}, [cand("cr1", false)])).ok).toBe(false);
    expect(approvable(detail({ candidate_credit_id: "other" }, [cand("cr1")])).ok).toBe(false);
    expect(approvable(detail({ candidate_credit_id: null }, [cand("cr1")])).ok).toBe(false);
  });
});

describe("runSequentially", () => {
  it("runs in order, one at a time", async () => {
    const order: string[] = [];
    let running = 0;
    let maxRunning = 0;
    const res = await runSequentially(["a", "b", "c"], (x) => x, async (x) => {
      running++;
      maxRunning = Math.max(maxRunning, running);
      await new Promise((r) => setTimeout(r, 1));
      order.push(x);
      running--;
    });
    expect(order).toEqual(["a", "b", "c"]);
    expect(maxRunning).toBe(1);
    expect(res.every((r) => r.ok)).toBe(true);
  });
  it("keeps going after a failure and reports every item", async () => {
    const seen: number[] = [];
    const res = await runSequentially(["a", "b", "c"], (x) => x, async (x) => {
      if (x === "b") throw new Error("last four do not match");
    }, (d) => seen.push(d));
    expect(res.map((r) => r.ok)).toEqual([true, false, true]);
    expect(res[1].message).toBe("last four do not match");
    expect(seen).toEqual([1, 2, 3]);
  });
});

describe("summarise", () => {
  it("is plain when all went through and names problems when not", () => {
    expect(summarise([{ id: "a", ok: true, message: "" }], "Rejected")).toBe("Rejected 1 claim.");
    const s = summarise(
      [
        { id: "a", ok: true, message: "" },
        { id: "b", ok: false, message: "needs a second approver" },
      ],
      "Approved",
    );
    expect(s).toMatch(/Approved 1 of 2/);
    expect(s).toMatch(/second approver/);
  });
});

describe("selection", () => {
  it("toggles, selects all visible, and prunes ids that left the list", () => {
    let s = toggle(new Set<string>(), "a");
    expect([...s]).toEqual(["a"]);
    s = toggle(s, "a");
    expect(s.size).toBe(0);
    expect(toggleAll(new Set(), ["a", "b"]).size).toBe(2);
    expect(toggleAll(new Set(["a", "b"]), ["a", "b"]).size).toBe(0);
    expect([...pruneSelection(new Set(["a", "z"]), ["a", "b"])]).toEqual(["a"]);
  });
  it("needs exactly four characters for the typed check", () => {
    expect(last4Ready("A12B")).toBe(true);
    expect(last4Ready("A12")).toBe(false);
    expect(last4Ready("  ")).toBe(false);
  });
});
