// Bulk actions on the review queue. The rules live here, away from the screen, so they can be tested:
// who may be approved in bulk, how a batch is run, and how the outcome is told to the reviewer.
//
// Nothing here weakens the single-claim safeguards: every call goes to the same endpoint, one claim at
// a time, so the server still checks the typed last four characters, open fraud alerts, hard gates,
// second-approver limits and separation of duties. Bulk only saves clicks.

import type { Candidate, ReviewDetail } from "../api";
import { FLAG_REASONS } from "./triage";

const REVIEWABLE_FOR_BULK = ["DOCUMENT_VERIFIED", "AWAITING_FINANCIAL_CONFIRMATION", "FINANCIALLY_CONFIRMED", "PENDING_REVIEW"];

export type Eligibility = { ok: true; candidate: Candidate } | { ok: false; why: string };

/** Only a claim that is green, matched to a credit that passes every gate, and carries no flag. */
export function approvable(d: ReviewDetail): Eligibility {
  const c = d.claim;
  if (!REVIEWABLE_FOR_BULK.includes(c.state)) return { ok: false, why: "Not waiting for a decision" };
  if ((c.approval_tier ?? "").toUpperCase() !== "GREEN") return { ok: false, why: "Not green: open it and check" };
  if ((c.risk_level ?? "").toLowerCase() === "high") return { ok: false, why: "High fraud risk" };
  if (c.reason_codes.some((r) => FLAG_REASONS.has(r))) return { ok: false, why: "Flagged: open it and check" };
  const cand = d.candidates.find((x) => x.credit.credit_id === c.candidate_credit_id && x.passed);
  if (!cand) return { ok: false, why: "No matched credit passes every check" };
  return { ok: true, candidate: cand };
}

export type Result = { id: string; ok: boolean; message: string };

/** One at a time, in order. A failure never stops the rest, and no item is skipped silently. */
export async function runSequentially<T>(
  items: T[],
  idOf: (x: T) => string,
  act: (x: T) => Promise<string | void>,
  onProgress?: (done: number, total: number) => void,
): Promise<Result[]> {
  const out: Result[] = [];
  for (const [i, item] of items.entries()) {
    try {
      out.push({ id: idOf(item), ok: true, message: (await act(item)) || "Done" });
    } catch (e) {
      out.push({ id: idOf(item), ok: false, message: (e as Error).message || "Failed" });
    }
    onProgress?.(i + 1, items.length);
  }
  return out;
}

export function summarise(results: Result[], verb: string): string {
  const failed = results.filter((r) => !r.ok);
  const okCount = results.length - failed.length;
  if (!failed.length) return `${verb} ${okCount} claim${okCount === 1 ? "" : "s"}.`;
  return `${verb} ${okCount} of ${results.length}. ${failed.length} did not go through: ${failed
    .slice(0, 3)
    .map((f) => f.message)
    .join("; ")}${failed.length > 3 ? "; …" : ""}`;
}

/** The last four characters typed for a row are valid input only when there are exactly four. */
export const last4Ready = (v: string) => v.trim().length === 4;

/** Selection that survives sorting and filtering but never keeps ids that are no longer listed. */
export function pruneSelection(selected: Set<string>, visibleIds: string[]): Set<string> {
  const visible = new Set(visibleIds);
  return new Set([...selected].filter((id) => visible.has(id)));
}

export function toggle(selected: Set<string>, id: string): Set<string> {
  const next = new Set(selected);
  if (!next.delete(id)) next.add(id);
  return next;
}

export function toggleAll(selected: Set<string>, visibleIds: string[]): Set<string> {
  return visibleIds.every((id) => selected.has(id)) ? new Set() : new Set(visibleIds);
}
