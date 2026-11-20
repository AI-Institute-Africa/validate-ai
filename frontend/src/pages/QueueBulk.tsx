// Bulk actions for the review queue. Each action goes through the same single-claim endpoint, one
// claim at a time, so every server-side check still applies (see lib/bulk.ts).

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, money, post, type Claim, type ReviewDetail } from "../api";
import { Dialog } from "../components/Dialog";
import { approvable, last4Ready, runSequentially, summarise, type Eligibility, type Result } from "../lib/bulk";
import { REJECT_CONSEQUENCES, REJECT_PAYER_MESSAGE, REJECT_REASONS, REQUEST_INFO_NOTE } from "../lib/payerMessages";
import { humanize } from "../labels";
import { useToast, useUndo } from "../toast";

type Mode = null | "info" | "reject" | "approve";

export function BulkBar({ selected, onClear }: { selected: Claim[]; onClear: () => void }) {
  // The open dialog keeps its own copy of the claims: once they are approved or rejected they leave
  // the queue and the selection empties, but the reviewer must still be able to read the results.
  const [open, setOpen] = useState<{ mode: Exclude<Mode, null>; claims: Claim[] } | null>(null);
  const nav = useNavigate();
  const n = selected.length;
  const close = () => setOpen(null);
  return (
    <>
      {n > 0 && (
        <div className="bulk-bar" role="region" aria-label="Actions for the selected claims">
          <span className="bulk-count">{n} selected</span>
          <button type="button" className="ghost" onClick={() => setOpen({ mode: "info", claims: selected })}>Ask for more info</button>
          <button type="button" onClick={() => setOpen({ mode: "approve", claims: selected })}>Approve matched…</button>
          <button type="button" className="danger" onClick={() => setOpen({ mode: "reject", claims: selected })}>Reject…</button>
          <button type="button" className="ghost" onClick={() => nav(`/claims/${selected[0].claim_id}`, { state: { selection: selected.map((c) => c.claim_id) } })}>
            Review one by one →
          </button>
          <button type="button" className="ghost small" onClick={onClear}>Clear</button>
        </div>
      )}
      {open?.mode === "info" && <InfoDialog claims={open.claims} onClose={close} onSent={onClear} />}
      {open?.mode === "reject" && <RejectDialog claims={open.claims} onClose={close} onSent={onClear} />}
      {open?.mode === "approve" && <ApproveSheet claims={open.claims} onClose={close} onDone={onClear} />}
    </>
  );
}

function useAfterBatch() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ["queue"] });
    qc.invalidateQueries({ queryKey: ["claim"] });
  };
}

function InfoDialog({ claims, onClose, onSent }: { claims: Claim[]; onClose: () => void; onSent: () => void }) {
  const [message, setMessage] = useState("");
  const undo = useUndo();
  const toast = useToast();
  const refresh = useAfterBatch();
  const send = () => {
    const ids = claims.map((c) => c.claim_id);
    const text = message.trim(); // copied now: editing afterwards cannot change what is sent
    onClose();
    onSent();
    undo(`Asking ${ids.length} payer${ids.length === 1 ? "" : "s"} for more information`, async () => {
      const res = await runSequentially(ids, (x) => x, (id) => post(`/review/claims/${id}/request-info`, { message: text }).then(() => "Asked"));
      toast(res.every((r) => r.ok) ? "ok" : "err", summarise(res, "Asked"));
      refresh();
    });
  };
  return (
    <Dialog title={`Ask ${claims.length} payers for more information`} onClose={onClose}>
      <p className="small">{REQUEST_INFO_NOTE}</p>
      <label>Message to all {claims.length} payers
        <textarea rows={3} value={message} onChange={(e) => setMessage(e.target.value)} placeholder="For example: please send a clearer photo of the whole receipt." />
      </label>
      <p className="small">You get a few seconds to undo this after you press Send.</p>
      <div className="dialog-actions">
        <button type="button" className="ghost" onClick={onClose}>Cancel</button>
        <button type="button" disabled={message.trim().length < 3} onClick={send}>Send to {claims.length}</button>
      </div>
    </Dialog>
  );
}

function RejectDialog({ claims, onClose, onSent }: { claims: Claim[]; onClose: () => void; onSent: () => void }) {
  const [reason, setReason] = useState(REJECT_REASONS[0]);
  const [note, setNote] = useState("");
  const [checked, setChecked] = useState(false);
  const undo = useUndo();
  const toast = useToast();
  const refresh = useAfterBatch();
  const go = () => {
    const ids = claims.map((c) => c.claim_id);
    const body = { reason, note: note.trim() };
    onClose();
    onSent();
    undo(`Rejecting ${ids.length} claim${ids.length === 1 ? "" : "s"}`, async () => {
      const res = await runSequentially(ids, (x) => x, (id) => post(`/review/claims/${id}/reject`, body).then(() => "Rejected"));
      toast(res.every((r) => r.ok) ? "ok" : "err", summarise(res, "Rejected") + " A reject cannot be undone now.");
      refresh();
    });
  };
  return (
    <Dialog title={`Reject ${claims.length} claims?`} onClose={onClose}>
      <label>Reason (audit trail only)
        <select value={reason} onChange={(e) => setReason(e.target.value)}>
          {REJECT_REASONS.map((r) => <option key={r} value={r}>{humanize(r)}</option>)}
        </select>
      </label>
      <label>Note (required, kept in the audit trail)
        <input value={note} onChange={(e) => setNote(e.target.value)} />
      </label>
      <p className="small"><strong>Each payer will be told:</strong></p>
      <blockquote className="payer-msg">{REJECT_PAYER_MESSAGE}</blockquote>
      <ul className="small">{REJECT_CONSEQUENCES.map((x) => <li key={x}>{x}</li>)}</ul>
      <label className="check">
        <input type="checkbox" checked={checked} onChange={(e) => setChecked(e.target.checked)} />
        I have checked these {claims.length} claims and the same reason applies to all of them.
      </label>
      <p className="small">You get a few seconds to undo this. Once it is sent, a reject cannot be undone.</p>
      <div className="dialog-actions">
        <button type="button" className="ghost" onClick={onClose}>Cancel</button>
        <button type="button" className="danger" disabled={!checked || note.trim().length < 3} onClick={go}>Reject {claims.length}</button>
      </div>
    </Dialog>
  );
}

type Row = { claim: Claim; detail?: ReviewDetail; el?: Eligibility; error?: string };

function ApproveSheet({ claims, onClose, onDone }: { claims: Claim[]; onClose: () => void; onDone: () => void }) {
  const qc = useQueryClient();
  const refresh = useAfterBatch();
  const [rows, setRows] = useState<Row[] | null>(null);
  const [typed, setTyped] = useState<Record<string, string>>({});
  const [results, setResults] = useState<Result[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    void runSequentially(claims, (c) => c.claim_id, async (c) => {
      const detail = await qc.fetchQuery({ queryKey: ["claim", c.claim_id], queryFn: () => api<ReviewDetail>(`/review/claims/${c.claim_id}`), staleTime: 0 });
      if (alive) setRows((r) => [...(r ?? []), { claim: c, detail, el: approvable(detail) }]);
    }).then((res) => {
      if (!alive) return;
      const failed = res.filter((x) => !x.ok);
      if (failed.length) setRows((r) => [...(r ?? []), ...failed.map((f) => ({ claim: claims.find((c) => c.claim_id === f.id)!, error: f.message }))]);
      setRows((r) => r ?? []);
    });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const eligible = (rows ?? []).filter((r) => r.el?.ok);
  const ready = eligible.filter((r) => last4Ready(typed[r.claim.claim_id] ?? ""));

  const approve = async () => {
    const res = await runSequentially(ready, (r) => r.claim.claim_id, async (r) => {
      const cand = (r.el as { ok: true; candidate: { credit: { credit_id: string } } }).candidate;
      const out = await post<{ needs_second_approval: boolean }>(`/review/claims/${r.claim.claim_id}/confirm`, {
        credit_id: cand.credit.credit_id,
        txn_last4: (typed[r.claim.claim_id] ?? "").trim(),
        note: "Approved in a batch",
      });
      return out.needs_second_approval ? "First approval recorded: another approver must confirm" : "Approved";
    }, (done, total) => setBusy(`Confirming ${done} of ${total}…`));
    setBusy(null);
    setResults(res);
    refresh();
  };

  return (
    <Dialog title="Approve matched claims" wide onClose={() => { onClose(); if (results) onDone(); }}>
      {!results && (
        <>
          <p className="small">
            Only green claims matched to a credit that passes every check can be approved here. As on a single
            claim, you confirm each one by typing the <strong>last 4 characters of the transaction ID from the
            bank or provider record</strong>, not from the receipt. The server checks it again.
          </p>
          {rows === null && <p className="muted">Checking {claims.length} claims…</p>}
          {rows !== null && (
            <div className="table-wrap">
              <table className="bulk-table">
                <thead><tr><th>Claim</th><th>Matched credit</th><th>Last 4</th></tr></thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.claim.claim_id} className={r.el?.ok ? "" : "bulk-skip"}>
                      <td>{r.claim.claimant_ref}<div className="muted small">{money(r.claim.declared_amount_minor, r.claim.declared_currency)}</div></td>
                      {r.el?.ok ? (
                        <>
                          <td>
                            {money(r.el.candidate.credit.amount_minor, r.el.candidate.credit.currency)}
                            <div className="muted small">{new Date(r.el.candidate.credit.occurred_at).toLocaleString()} · {r.el.candidate.credit.narrative ?? r.el.candidate.credit.provider}</div>
                          </td>
                          <td>
                            <input
                              className="last4"
                              maxLength={4}
                              aria-label={`Last 4 characters for ${r.claim.claimant_ref}`}
                              value={typed[r.claim.claim_id] ?? ""}
                              onChange={(e) => setTyped({ ...typed, [r.claim.claim_id]: e.target.value })}
                            />
                          </td>
                        </>
                      ) : (
                        <td colSpan={2}>Skipped: {r.error ?? (r.el && !r.el.ok ? r.el.why : "")}</td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {busy && <p role="status">{busy}</p>}
          <div className="dialog-actions">
            <button type="button" className="ghost" onClick={onClose}>Cancel</button>
            <button type="button" disabled={!ready.length || !!busy} onClick={() => void approve()}>
              Approve {ready.length} of {eligible.length}
            </button>
          </div>
          {eligible.length > ready.length && ready.length > 0 && (
            <p className="small muted">Rows without 4 characters typed are left alone.</p>
          )}
        </>
      )}
      {results && (
        <>
          <p role="status"><strong>{summarise(results, "Approved")}</strong></p>
          <div className="table-wrap">
            <table className="bulk-table">
              <tbody>
                {results.map((r) => {
                  const row = rows?.find((x) => x.claim.claim_id === r.id);
                  return (
                    <tr key={r.id}>
                      <td>{row?.claim.claimant_ref}</td>
                      <td className={`bulk-result ${r.ok ? "ok" : "bad"}`}>{r.ok ? "✓" : "✕"} {r.message}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="dialog-actions"><button type="button" onClick={() => { onClose(); onDone(); }}>Close</button></div>
        </>
      )}
    </Dialog>
  );
}
