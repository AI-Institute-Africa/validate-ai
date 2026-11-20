import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, download, post } from "../api";
import { useToast } from "../toast";
import { Chip, Loading, PageHeader } from "../ui";
import { ReasonDialog } from "../components/ActionDialog";
import "./review.css";

type Overview = {
  data_region: string | null;
  storage_backend: string;
  api_docs_enabled: boolean;
  retention: { evidence_days: number | null; alert_text_days: number | null; kyc_image_days: number };
  ai: { enforced: boolean; allowed_hosts: string[]; endpoints: { use: string; url: string; model: string; external: boolean; allowed: boolean; api_key_set: boolean }[] };
  open_incidents: number;
  reporting_hours: number;
};
type Incident = { incident_id: string; kind: string; title: string; status: string; detected_at: string; due_at: string; reported_at: string | null; report_reference: string | null };

const days = (n: number | null) => (n == null ? "kept until removed by hand" : `${n} days`);

/** Where the data lives, how long it is kept, which models run, and the incident register. */
export default function Compliance() {
  const qc = useQueryClient();
  const toast = useToast();
  const ov = useQuery({ queryKey: ["compliance"], queryFn: () => api<Overview>("/admin/compliance") });
  const list = useQuery({ queryKey: ["incidents"], queryFn: () => api<Incident[]>("/admin/incidents"), refetchInterval: 60000 });
  const [kind, setKind] = useState("breach");
  const [title, setTitle] = useState("");
  const [summary, setSummary] = useState("");
  const [reporting, setReporting] = useState<Incident | null>(null);
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["incidents"] });
    qc.invalidateQueries({ queryKey: ["compliance"] });
  };
  const create = useMutation({
    mutationFn: () => post("/admin/incidents", { kind, title, summary }),
    onSuccess: () => { toast("ok", "Incident recorded. The 24-hour clock has started."); setTitle(""); setSummary(""); refresh(); },
    onError: (e) => toast("err", (e as Error).message),
  });
  const reported = useMutation({
    mutationFn: (v: { id: string; reference: string }) => post(`/admin/incidents/${v.id}/reported`, { reference: v.reference }),
    onSuccess: () => { toast("ok", "Marked as reported."); refresh(); },
    onError: (e) => toast("err", (e as Error).message),
  });
  if (ov.isLoading) return <Loading lines={5} />;
  const o = ov.data;
  return (
    <section className="rv">
      <PageHeader title="Compliance" sub="Where the data lives, how long it is kept, which models run, and personal-data incidents." />
      {ov.error && <p className="error">{(ov.error as Error).message}</p>}
      {o && (
        <div className="card">
          <h3>Hosting and retention</h3>
          <dl className="rv-facts">
            <div><dt>Data region</dt><dd>{o.data_region ?? <Chip tone="warn">not set</Chip>}</dd></div>
            <div><dt>File storage</dt><dd>{o.storage_backend}</dd></div>
            <div><dt>Payment files</dt><dd>{days(o.retention.evidence_days)}</dd></div>
            <div><dt>Raw alert text</dt><dd>{days(o.retention.alert_text_days)}</dd></div>
            <div><dt>ID images</dt><dd>{days(o.retention.kyc_image_days)}</dd></div>
            <div><dt>API docs page</dt><dd>{o.api_docs_enabled ? "on" : "off"}</dd></div>
          </dl>
          <h3>Models</h3>
          <p className="rv-help">No receipt, ID photo or face is sent to an outside AI service. {o.ai.enforced ? "This is enforced: a call to any other host is refused." : "Development mode: not enforced."}</p>
          <ul className="small">
            {o.ai.endpoints.map((e) => (
              <li key={e.url}>
                {e.model} at <code>{e.url}</code>{" "}
                {e.external ? (e.allowed ? <Chip tone="warn">outside, allowed</Chip> : <Chip tone="bad">outside, blocked</Chip>) : <Chip tone="ok">on our servers</Chip>}
                {e.api_key_set && <Chip tone="bad">API key set</Chip>}
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="card">
        <h3>Incidents</h3>
        <p className="rv-help">A personal-data breach is to be reported within {o?.reporting_hours ?? 24} hours of detection (confirm the rule with counsel). Record one as soon as it is found; admins are reminded at 12 and 20 hours until it is reported.</p>
        {list.isLoading && <Loading lines={2} />}
        <ul className="rv-history">
          {list.data?.map((i) => (
            <li key={i.incident_id}>
              <div className="what">{i.title} <Chip tone={i.status === "open" ? "warn" : "ok"}>{i.status}</Chip> <span className="muted small">{i.kind}</span></div>
              <div className="when">Detected {new Date(i.detected_at).toLocaleString()} · due {new Date(i.due_at).toLocaleString()}{i.reported_at ? ` · reported ${new Date(i.reported_at).toLocaleString()} (${i.report_reference})` : ""}</div>
              <div className="inline">
                <button type="button" className="ghost small" onClick={() => void download(`/admin/incidents/${i.incident_id}/affected.csv`)}>Affected records (CSV)</button>
                {i.status === "open" && (
                  <button type="button" className="secondary small" onClick={() => setReporting(i)}>Mark as reported</button>
                )}
              </div>
            </li>
          ))}
          {list.data?.length === 0 && <li className="muted">No incidents recorded.</li>}
        </ul>
        <h4>Record an incident</h4>
        <form className="inline" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
          <select value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Kind">
            <option value="breach">Breach</option>
            <option value="near_miss">Near miss</option>
            <option value="other">Other</option>
          </select>
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Short title (5+ characters)" aria-label="Title" />
          <input value={summary} onChange={(e) => setSummary(e.target.value)} placeholder="What happened (10+ characters)" aria-label="Summary" />
          <button disabled={title.trim().length < 5 || summary.trim().length < 10 || create.isPending}>Record</button>
        </form>
      </div>
      {reporting && (
        <ReasonDialog
          title="Mark incident as reported"
          label="Regulator's reference"
          message={`Record the reference for “${reporting.title}”. It is kept in the incident audit trail.`}
          placeholder="e.g. REG-2026-001"
          confirmLabel="Mark as reported"
          onClose={() => setReporting(null)}
          onConfirm={(reference) => reported.mutate({ id: reporting.incident_id, reference })}
        />
      )}
    </section>
  );
}
