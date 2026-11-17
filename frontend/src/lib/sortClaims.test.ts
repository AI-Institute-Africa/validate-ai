import { describe, expect, it } from "vitest";
import type { Claim } from "../api";
import { DEFAULT_SORT, ariaSort, nextSort, sortClaims } from "./sortClaims";

const c = (id: string, over: Partial<Claim>): Claim =>
  ({ claim_id: id, created_at: "2026-11-01T10:00:00Z", declared_amount_minor: 100, approval_tier: "AMBER", risk_score: 0, state: "PENDING_REVIEW", ...over }) as Claim;

const rows = [
  c("new", { created_at: "2026-11-03T10:00:00Z", declared_amount_minor: 500, approval_tier: "GREEN", risk_score: 10 }),
  c("old", { created_at: "2026-11-01T10:00:00Z", declared_amount_minor: 100, approval_tier: "RED", risk_score: 90 }),
  c("mid", { created_at: "2026-11-02T10:00:00Z", declared_amount_minor: null, approval_tier: null, risk_score: null }),
];

describe("sortClaims", () => {
  it("defaults to the longest-waiting claim first", () => {
    expect(sortClaims(rows, DEFAULT_SORT).map((r) => r.claim_id)).toEqual(["old", "mid", "new"]);
    expect(sortClaims(rows, { key: "waiting", dir: "asc" }).map((r) => r.claim_id)).toEqual(["new", "mid", "old"]);
  });
  it("sorts by amount, level and risk, with missing values last when descending", () => {
    expect(sortClaims(rows, { key: "declared", dir: "desc" }).map((r) => r.claim_id)).toEqual(["new", "old", "mid"]);
    expect(sortClaims(rows, { key: "level", dir: "desc" }).map((r) => r.claim_id)).toEqual(["old", "new", "mid"]);
    expect(sortClaims(rows, { key: "risk", dir: "desc" }).map((r) => r.claim_id)).toEqual(["old", "new", "mid"]);
  });
  it("is stable: equal values keep the server's order", () => {
    const same = [c("a", {}), c("b", {}), c("c", {})];
    expect(sortClaims(same, { key: "risk", dir: "desc" }).map((r) => r.claim_id)).toEqual(["a", "b", "c"]);
  });
  it("does not change the input array", () => {
    const copy = [...rows];
    sortClaims(rows, { key: "declared", dir: "asc" });
    expect(rows).toEqual(copy);
  });
});

describe("header state", () => {
  it("clicking the same column flips it; a new column starts descending", () => {
    expect(nextSort({ key: "waiting", dir: "desc" }, "waiting")).toEqual({ key: "waiting", dir: "asc" });
    expect(nextSort({ key: "waiting", dir: "asc" }, "risk")).toEqual({ key: "risk", dir: "desc" });
  });
  it("reports aria-sort only for the active column", () => {
    expect(ariaSort({ key: "risk", dir: "asc" }, "risk")).toBe("ascending");
    expect(ariaSort({ key: "risk", dir: "asc" }, "level")).toBe("none");
  });
});
