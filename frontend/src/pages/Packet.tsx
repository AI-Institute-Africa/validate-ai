import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api, money } from "../api";
import { Menu } from "../components/Menu";
import { Loading, PageHeader, Reasons } from "../ui";
import "./review.css";

type Packet = {
  packet_version: number;
  exported_at: string;
  exported_by: string;
  claim: { claim_id: string; channel: string; claimant_ref: string; declared_amount_minor: number | null; declared_currency: string | null; declared_reference: string | null; state: string; evidence_tier: string; approval_tier: string | null; reason_codes: string[]; created_at: string };
  invoice: { description: string; amount_minor: number; currency: string; payment_code: string } | null;
  official_rate: { ask?: string; rate_date?: string; source_sha256?: string | null; carried_forward_from?: string | null } | null;
  decisions: { decision_id: string; outcome: string; actor_type: string; actor_id: string; reason_codes: string[]; policy_version: string; note: string | null; created_at: string }[];
  runs: { run_id: string; created_at: string; pipeline_version: string; policy_version: string; model_versions: Record<string, unknown>; outcome: string }[];
  evidence: { evidence_id: string; sha256: string; content_type: string; size_bytes: number }[];
  fields_read: { name: string; raw_value: string | null; extractor: string; extractor_version: string; agreed: boolean; corrected_by: string | null; correction_reason: string | null }[];
  allocations: { allocation_id: string; kind: string; amount_minor: number; currency: string; created_by: string; created_at: string }[];
  audit_events: { action: string; actor: string; at: string }[];
};

/** One claim's decision record for an auditor: print it or save it as JSON. */
export default function PacketPage() {
  const { id = "" } = useParams();
  const q = useQuery({ queryKey: ["packet", id], queryFn: () => api<Packet>(`/review/claims/${id}/audit-packet`) });
  if (q.isLoading) return <Loading lines={6} />;
  if (q.error || !q.data) return <p className="error">{(q.error as Error)?.message ?? "Not found"}</p>;
  const p = q.data;
  const save = () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(p, null, 2)], { type: "application/json" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `audit-packet-${p.claim.claim_id.slice(0, 8)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };
  return (
    <section className="rv packet">
      <PageHeader
        title="Audit packet"
        sub={`Claim ${p.claim.claim_id.slice(0, 8)} · exported ${new Date(p.exported_at).toLocaleString()} by ${p.exported_by}`}
        actions={<span className="no-print"><Menu label="Export" items={[{ label: "Print", onSelect: () => window.print() }, { label: "Save JSON", onSelect: save }]} /> <Link className="btn secondary" to={`/claims/${p.claim.claim_id}`}>← Claim</Link></span>}
      />
      <div className="card">
        <h3>Claim</h3>
        <p>
          {p.claim.declared_amount_minor == null ? "No amount typed" : money(p.claim.declared_amount_minor, p.claim.declared_currency)} declared by <strong>{p.claim.claimant_ref}</strong> via {p.claim.channel}.
          State <strong>{p.claim.state}</strong>, evidence {p.claim.evidence_tier}, level {p.claim.approval_tier ?? "—"}.
        </p>
        {p.invoice && <p className="small muted">Invoice: {p.invoice.description} · {money(p.invoice.amount_minor, p.invoice.currency)} · code {p.invoice.payment_code}</p>}
        <Reasons codes={p.claim.reason_codes} />
        {p.official_rate?.ask && <p className="small">Official rate used: {p.official_rate.ask} ZWG per USD ({p.official_rate.rate_date}{p.official_rate.carried_forward_from ? `, carried from ${p.official_rate.carried_forward_from}` : ""}).</p>}
      </div>
      <div className="card">
        <h3>Decisions</h3>
        <ul className="rv-history">
          {p.decisions.map((d) => (
            <li key={d.decision_id}>
              <div className="what">{d.outcome} <span className="muted small">by {d.actor_type} {d.actor_id}</span></div>
              <div className="when">{new Date(d.created_at).toLocaleString()} · policy {d.policy_version}</div>
              {d.reason_codes.length > 0 && <Reasons codes={d.reason_codes} />}
              {d.note && <div className="note">“{d.note}”</div>}
            </li>
          ))}
        </ul>
      </div>
      <div className="card">
        <h3>Readers and models</h3>
        <ul className="rv-history">
          {p.runs.map((r) => (
            <li key={r.run_id}>
              <div className="what">{r.outcome} <span className="muted small">pipeline {r.pipeline_version} · policy {r.policy_version}</span></div>
              <div className="when">{new Date(r.created_at).toLocaleString()}</div>
              <div className="small muted">{Object.entries(r.model_versions).filter(([k]) => k !== "guardrails").map(([k, v]) => `${k} ${String(v)}`).join(" · ")}</div>
            </li>
          ))}
        </ul>
      </div>
      <div className="card">
        <h3>Evidence (fingerprints only)</h3>
        <ul className="small">{p.evidence.map((e) => <li key={e.evidence_id}>{e.content_type}, {e.size_bytes} bytes, SHA-256 <code>{e.sha256}</code></li>)}</ul>
        <h3>What was read</h3>
        <div className="table-wrap">
          <table className="rv-compare">
            <thead><tr><th>Field</th><th>Value</th><th>Read by</th><th /></tr></thead>
            <tbody>
              {p.fields_read.map((f, i) => (
                <tr key={i}><td>{f.name}</td><td>{f.raw_value ?? "—"}</td><td>{f.extractor} {f.extractor_version}</td><td>{f.corrected_by ? `corrected by ${f.corrected_by}: ${f.correction_reason}` : f.agreed ? "readers agree" : "not agreed"}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div className="card">
        <h3>Money and audit trail</h3>
        <ul className="small">{p.allocations.map((a) => <li key={a.allocation_id}>{a.kind} {money(a.amount_minor, a.currency)} by {a.created_by}, {new Date(a.created_at).toLocaleString()}</li>)}</ul>
        <ul className="small muted">{p.audit_events.map((e, i) => <li key={i}>{new Date(e.at).toLocaleString()} · {e.action} · {e.actor}</li>)}</ul>
      </div>
    </section>
  );
}
