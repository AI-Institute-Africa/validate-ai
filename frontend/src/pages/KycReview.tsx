import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, blobUrl, hasRole, post } from "../api";
import { CHECKS, DOC_TYPES, FIELD_LABELS } from "../labels";
import { useToast } from "../toast";
import { EmptyState, Loading, PageHeader, Reasons, StateChip } from "../ui";
import { ReasonDialog } from "../components/ActionDialog";
import { CardCell, CardTable } from "../components/CardTable";

type QueueRow = {
  kyc_id: string;
  subject_type: string;
  subject_ref: string;
  created_at: string;
  doc_type: string | null;
  issuing_country: string | null;
  reason_codes: string[];
  face_score: number | null;
};
type Detail = QueueRow & {
  state: string;
  fields: { values: Record<string, string | null>; agreed: Record<string, boolean>; sources: Record<string, Record<string, string | null>> };
  checks: { name: string; ok: boolean | null; [k: string]: unknown }[];
  scores: { ocr_agreement: number | null; mrz_valid: boolean | null; face: number | null; liveness: number | null };
  evidence: { role: string; purged: boolean }[];
};
type Auto = {
  mode: string;
  enabled: boolean;
  audit_pct: number;
  summary: { verified: number; sampled: number; audited: number; overturned: number; overturn_rate: number | null };
  verifications: {
    kyc_id: string;
    verified_at: string;
    subject_type: string | null;
    subject_ref: string | null;
    doc_type: string | null;
    face_score: number | null;
    sampled: boolean;
    verdict: { outcome: string; by: string; note: string | null } | null;
  }[];
};

function Img({ id, role, label }: { id: string; role: string; label: string }) {
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let url: string | null = null;
    blobUrl(`/kyc/verifications/${id}/evidence/${role}`)
      .then((u) => { url = u; setSrc(u); })
      .catch(() => setFailed(true));
    return () => { if (url) URL.revokeObjectURL(url); };
  }, [id, role]);
  return (
    <figure>
      {src ? <img src={src} alt={label} /> : <div className="skeleton-line" style={{ height: 180, borderRadius: 10 }}>{failed ? "Image not available" : ""}</div>}
      <figcaption>{label}</figcaption>
    </figure>
  );
}

function Meter({ label, value, good, fmt }: { label: string; value: number | null; good: number; fmt?: (v: number) => string }) {
  const pct = value === null ? 0 : Math.max(0, Math.min(1, value)) * 100;
  const ok = value !== null && value >= good;
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between" }}>
        <span>{label}</span>
        <b>{value === null ? "n/a" : fmt ? fmt(value) : value.toFixed(2)}</b>
      </div>
      <div className="meter" aria-hidden>
        <i style={{ width: `${pct}%`, background: value === null ? "var(--muted)" : ok ? "var(--ok)" : "var(--warn)" }} />
      </div>
    </div>
  );
}

// Reviewer view: everything the readers and the face matcher produced, beside the images.
// A disagreement between sources is shown, never hidden. The reviewer decides.
function Review({ id, onDone }: { id: string; onDone: () => void }) {
  const toast = useToast();
  const q = useQuery({ queryKey: ["kyc", id], queryFn: () => api<Detail>(`/kyc/verifications/${id}`) });
  const decide = useMutation({
    mutationFn: (v: { outcome: string; note: string | null }) => post(`/kyc/review/${id}/decision`, v),
    onSuccess: () => { toast("ok", "Decision recorded."); onDone(); },
    onError: (e) => toast("err", (e as Error).message),
  });
  const [deciding, setDeciding] = useState<string | null>(null);
  if (q.isLoading) return <Loading lines={5} />;
  if (!q.data) return <p className="error">{(q.error as Error)?.message ?? "Not found"}</p>;
  const d = q.data;
  const values = d.fields?.values ?? {};
  // only fields that were actually read: a field that is not on this document is not a failure
  const rows = Object.keys(FIELD_LABELS).filter((k) => values[k] != null);
  const open = d.state === "NEEDS_REVIEW";
  return (
    <div className="card">
      <div className="toolbar" style={{ justifyContent: "space-between" }}>
        <h2 style={{ margin: 0 }}>
          {d.subject_type}: {d.subject_ref}
        </h2>
        <StateChip state={d.state} />
      </div>
      <p className="muted small">
        {d.doc_type ? DOC_TYPES[d.doc_type] ?? d.doc_type : "Unknown document"}
        {d.issuing_country ? ` · issued by ${d.issuing_country}` : ""}
      </p>
      <h3>Why it needs a person</h3>
      <Reasons codes={d.reason_codes} empty="No blockers recorded." />
      <div className="compare" style={{ marginTop: 14 }}>
        <Img id={id} role="front" label="The document" />
        <Img id={id} role="selfie" label="The selfie" />
      </div>
      <div className="grid cols-2" style={{ marginTop: 14 }}>
        <div>
          <h3>Scores</h3>
          <Meter label="Face match" value={d.scores.face} good={0.6} />
          <Meter label="Looks like a live capture" value={d.scores.liveness} good={0.7} />
          <Meter label="Readers agree on key fields" value={d.scores.ocr_agreement} good={1} fmt={(v) => `${Math.round(v * 100)}%`} />
          <p className="small muted">
            Machine-readable zone: {d.scores.mrz_valid === null ? "not on this document" : d.scores.mrz_valid ? "check digits valid" : "check digits FAILED"}
          </p>
        </div>
        <div>
          <h3>Checks run</h3>
          <ul className="checks">
            {d.checks.map((c) => (
              <li key={c.name}>
                <span className={`mk ${c.ok === null ? "na" : c.ok ? "ok" : "bad"}`} aria-hidden>{c.ok === null ? "–" : c.ok ? "✓" : "✕"}</span>
                {CHECKS[c.name] ?? c.name}
              </li>
            ))}
          </ul>
        </div>
      </div>
      <h3 style={{ marginTop: 14 }}>What was read</h3>
      <CardTable caption="What was read from the ID">
        <thead>
          <tr><th>Field</th><th>Chosen value</th><th>Two sources agree</th><th>Each source read</th></tr>
        </thead>
        <tbody>
          {rows.map((k) => (
            <tr key={k}>
              <CardCell label="Field">{FIELD_LABELS[k]}</CardCell>
              <CardCell label="Chosen value"><b>{values[k] ?? "—"}</b></CardCell>
              <CardCell label="Two sources agree">{d.fields.agreed[k] ? <span className="chip2 tone-ok">Yes</span> : <span className="chip2 tone-warn">No</span>}</CardCell>
              <CardCell label="Each source read" wide className="small muted">{Object.entries(d.fields.sources[k] ?? {}).map(([s, x]) => `${s.replace(/^fake_id_/, "").replace(/^id_/, "")}: ${x}`).join(" · ")}</CardCell>
            </tr>
          ))}
        </tbody>
      </CardTable>
      {open && hasRole("reviewer") && (
        <div className="scn-actions" style={{ marginTop: 16 }}>
          <button type="button" disabled={decide.isPending} onClick={() => setDeciding("VERIFIED")}>Verify</button>
          <button type="button" className="secondary" disabled={decide.isPending} onClick={() => setDeciding("NEEDS_INFORMATION")}>Ask for new photos</button>
          <button type="button" className="danger" disabled={decide.isPending} onClick={() => setDeciding("REJECTED")}>Reject</button>
        </div>
      )}
      {!open && <p className="muted small" style={{ marginTop: 12 }}>This check is {d.state.toLowerCase().replace(/_/g, " ")}; no decision is pending.</p>}
      {deciding && (
        <ReasonDialog
          title={deciding === "VERIFIED" ? "Verify this identity?" : deciding === "NEEDS_INFORMATION" ? "Ask for new photos?" : "Reject this identity?"}
          label={deciding === "VERIFIED" ? "Note (optional)" : "Reason (required, shown in the audit trail)"}
          optional={deciding === "VERIFIED"}
          confirmLabel={deciding === "VERIFIED" ? "Verify" : deciding === "NEEDS_INFORMATION" ? "Ask for photos" : "Reject"}
          danger={deciding === "REJECTED"}
          onClose={() => setDeciding(null)}
          onConfirm={(note) => decide.mutate({ outcome: deciding, note: note || null })}
        />
      )}
    </div>
  );
}

export default function KycReview() {
  const qc = useQueryClient();
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const [overturning, setOverturning] = useState<{ id: string; ref: string | null } | null>(null);
  const open = params.get("open");
  const setOpen = (id: string | null) => setParams(id ? { open: id } : {}, { replace: true });
  const queue = useQuery({ queryKey: ["kyc-queue"], queryFn: () => api<QueueRow[]>("/kyc/review/queue"), refetchInterval: 20000 });
  const auto = useQuery({ queryKey: ["kyc-auto"], queryFn: () => api<Auto>("/kyc/review/auto-verified") });
  const verdict = useMutation({
    mutationFn: (v: { id: string; verdict: "ok" | "overturned"; note: string | null }) =>
      post(`/kyc/review/${v.id}/audit-verdict`, { verdict: v.verdict, note: v.note }),
    onSuccess: () => { toast("ok", "Verdict recorded. Revoke the verification separately if it was wrong."); qc.invalidateQueries({ queryKey: ["kyc-auto"] }); },
    onError: (e) => toast("err", (e as Error).message),
  });
  const done = () => { setOpen(null); qc.invalidateQueries({ queryKey: ["kyc-queue"] }); qc.invalidateQueries({ queryKey: ["kyc-auto"] }); qc.invalidateQueries({ queryKey: ["kyc-count"] }); };
  const a = auto.data;
  return (
    <div>
      <PageHeader title="Identity checks" sub="Cases the rules did not clear on their own. Open one to see the documents, every score and the reason." />
      {queue.error && <p className="error">{(queue.error as Error).message}</p>}
      {queue.isLoading && <Loading />}
      {queue.data?.length === 0 && (
        <EmptyState icon="✓" title="Nothing waiting">Every identity check has been decided. New ones appear here as people submit them.</EmptyState>
      )}
      {!!queue.data?.length && (
        <div className="card" style={{ padding: 0 }}>
          <CardTable caption="Identity checks waiting for a person">
            <thead>
              <tr><th>Submitted</th><th>Subject</th><th>Document</th><th>Face match</th><th>Why</th></tr>
            </thead>
            <tbody>
              {queue.data.map((r) => (
                <tr
                  key={r.kyc_id}
                  className="rv-click"
                  tabIndex={0}
                  aria-label={`Open identity check for ${r.subject_ref}`}
                  onClick={() => setOpen(r.kyc_id)}
                  onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setOpen(r.kyc_id); } }}
                  style={{ cursor: "pointer", background: open === r.kyc_id ? "color-mix(in srgb, var(--accent) 8%, transparent)" : undefined }}
                >
                  <CardCell label="Submitted">{new Date(r.created_at).toLocaleString()}</CardCell>
                  <CardCell label="Subject">{r.subject_type}: {r.subject_ref}</CardCell>
                  <CardCell label="Document">{r.doc_type ? DOC_TYPES[r.doc_type] ?? r.doc_type : "?"}</CardCell>
                  <CardCell label="Face match">{r.face_score?.toFixed(2) ?? "n/a"}</CardCell>
                  <CardCell label="Why" wide className="small muted">{r.reason_codes.join(", ")}</CardCell>
                </tr>
              ))}
            </tbody>
          </CardTable>
        </div>
      )}
      {open && <Review key={open} id={open} onDone={done} />}
      {a && (
        <div className="card">
          <h2>Verified automatically</h2>
          <p className="muted small">
            Mode: <b>{a.mode}</b>
            {a.mode === "shadow" && " (recording what the rules would do; nothing is verified automatically)"}. {a.audit_pct}% are sampled
            for a person to check. The overturn rate decides whether the rules can be widened.
          </p>
          <p>
            {a.summary.verified} verified · {a.summary.sampled} sampled · {a.summary.audited} audited · {a.summary.overturned} overturned
            {a.summary.overturn_rate !== null && <> · overturn rate <b>{(a.summary.overturn_rate * 100).toFixed(1)}%</b></>}
          </p>
          <CardTable caption="Verified automatically">
            <thead><tr><th>Verified</th><th>Subject</th><th>Face match</th><th>Audit</th><th /></tr></thead>
            <tbody>
              {a.verifications.length === 0 && <tr><CardCell label="" wide colSpan={5} className="muted">None yet.</CardCell></tr>}
              {a.verifications.map((v) => (
                <tr key={v.kyc_id}>
                  <CardCell label="Verified"><button type="button" className="link" onClick={() => setOpen(v.kyc_id)}>{new Date(v.verified_at).toLocaleString()}</button></CardCell>
                  <CardCell label="Subject">{v.subject_type}: {v.subject_ref}</CardCell>
                  <CardCell label="Face match">{v.face_score?.toFixed(2) ?? "n/a"}</CardCell>
                  <CardCell label="Audit">{v.verdict ? `${v.verdict.outcome === "KYC_AUDIT_OK" ? "Correct" : "Overturned"} by ${v.verdict.by}` : v.sampled ? "In the sample: please check" : "Not sampled"}</CardCell>
                  <CardCell label="">
                    {!v.verdict && hasRole("reviewer") && (
                      <>
                        <button type="button" className="secondary small" onClick={() => verdict.mutate({ id: v.kyc_id, verdict: "ok", note: null })}>Correct</button>{" "}
                        <button type="button" className="danger small" onClick={() => setOverturning({ id: v.kyc_id, ref: v.subject_ref })}>Overturn</button>
                      </>
                    )}
                  </CardCell>
                </tr>
              ))}
            </tbody>
          </CardTable>
        </div>
      )}
      {overturning && (
        <ReasonDialog
          title="Overturn this verification?"
          label="What was wrong?"
          message={overturning.ref ? `The verification for ${overturning.ref} will be marked overturned. Revoke it separately if it was wrong.` : "The verification will be marked overturned. Revoke it separately if it was wrong."}
          confirmLabel="Mark overturned"
          danger
          onClose={() => setOverturning(null)}
          onConfirm={(note) => verdict.mutate({ id: overturning.id, verdict: "overturned", note })}
        />
      )}
    </div>
  );
}
