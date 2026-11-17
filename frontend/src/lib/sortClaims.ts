// Queue sorting. Pure and stable, so the order a reviewer sees is predictable and testable.

import type { Claim } from "../api";

export type SortKey = "waiting" | "declared" | "level" | "risk" | "status";
export type SortDir = "asc" | "desc";
export type Sort = { key: SortKey; dir: SortDir };

// Default: the oldest claim first, because it has waited longest.
export const DEFAULT_SORT: Sort = { key: "waiting", dir: "desc" };

const LEVEL: Record<string, number> = { RED: 3, AMBER: 2, GREEN: 1 };

function value(c: Claim, key: SortKey): number | string {
  switch (key) {
    case "waiting":
      return Date.parse(c.created_at); // "desc" = longest waiting first (oldest timestamp)
    case "declared":
      return c.declared_amount_minor ?? -1;
    case "level":
      return LEVEL[(c.approval_tier ?? "").toUpperCase()] ?? 0;
    case "risk":
      return c.risk_score ?? -1;
    case "status":
      return c.state;
  }
}

export function sortClaims(rows: Claim[], sort: Sort): Claim[] {
  const dir = sort.dir === "asc" ? 1 : -1;
  // for "waiting", an older timestamp means a longer wait, so the direction is flipped
  const flip = sort.key === "waiting" ? -1 : 1;
  return rows
    .map((c, i) => ({ c, i }))
    .sort((a, b) => {
      const x = value(a.c, sort.key);
      const y = value(b.c, sort.key);
      const cmp = x < y ? -1 : x > y ? 1 : 0;
      return cmp !== 0 ? cmp * dir * flip : a.i - b.i; // equal values keep their server order
    })
    .map((x) => x.c);
}

export function nextSort(current: Sort, key: SortKey): Sort {
  if (current.key !== key) return { key, dir: "desc" };
  return { key, dir: current.dir === "desc" ? "asc" : "desc" };
}

export function ariaSort(current: Sort, key: SortKey): "ascending" | "descending" | "none" {
  if (current.key !== key) return "none";
  return current.dir === "asc" ? "ascending" : "descending";
}
