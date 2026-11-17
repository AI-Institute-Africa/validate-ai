import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, hasRole, post } from "../api";
import { useToast } from "../toast";
import { Chip, Loading, PageHeader } from "../ui";
import "./review.css";

type Rate = { rate_date: string; pair: string; ask: string; bid: string; mid: string; method: string; source_url: string | null; entered_by: string | null; reason: string | null };
type Attempt = { for_date: string; outcome: string; detail: string | null; method: string | null; attempted_at: string };
type Status = { enabled: boolean; fetch_hours_utc: string; recent_rates: Rate[]; recent_attempts: Attempt[] };

const TONE: Record<string, "ok" | "warn" | "bad" | "neutral"> = { stored: "ok", republished: "warn", already: "neutral", missing: "warn", layout_changed: "bad" };

/** The Reserve Bank's official ZWG per USD ask rate: health of the daily fetch, and manual entry. */
export default function Fx() {
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery({ queryKey: ["fx-status"], queryFn: () => api<Status>("/admin/fx/status"), refetchInterval: 60000 });
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [ask, setAsk] = useState("");
  const [reason, setReason] = useState("");
  const save = useMutation({
    mutationFn: () => post("/admin/fx/manual", { rate_date: date, ask, reason }),
    onSuccess: () => {
      toast("ok", "Rate saved.");
      setAsk("");
      setReason("");
      qc.invalidateQueries({ queryKey: ["fx-status"] });
    },
    onError: (e) => toast("err", (e as Error).message),
  });
  if (q.isLoading) return <Loading lines={4} />;
  const s = q.data;
  return (
    <section className="rv">
      <PageHeader
        title="Official exchange rate"
        sub="The Reserve Bank of Zimbabwe's interbank ask rate (ZWG per 1 USD), fetched each working day with the PDF kept as evidence."
      />
      {q.error && <p className="error">{(q.error as Error).message}</p>}
      {s && (
        <>
          <div className="card">
            <p>
              Daily fetch: <Chip tone={s.enabled ? "ok" : "warn"}>{s.enabled ? "on" : "off"}</Chip>{" "}
              <span className="muted small">weekdays, tries hourly during {s.fetch_hours_utc} UTC until the file appears. Weekends carry the last rate forward.</span>
            </p>
            <h3>Recent rates</h3>
            <div className="table-wrap">
              <table>
                <thead><tr><th>Date</th><th className="num">Ask</th><th className="num">Bid</th><th>How</th><th>Source</th></tr></thead>
                <tbody>
                  {s.recent_rates.map((r, i) => (
                    <tr key={`${r.rate_date}-${i}`}>
                      <td>{r.rate_date}</td>
                      <td className="num"><strong>{Number(r.ask).toFixed(4)}</strong></td>
                      <td className="num">{Number(r.bid).toFixed(4)}</td>
                      <td>{r.method === "manual" ? <Chip tone="warn" title={r.reason ?? ""}>entered by {r.entered_by}</Chip> : r.method}</td>
                      <td className="small">{r.source_url ? <a href={r.source_url} target="_blank" rel="noreferrer">RBZ file</a> : "—"}</td>
                    </tr>
                  ))}
                  {s.recent_rates.length === 0 && <tr><td colSpan={5} className="muted">No rate stored yet.</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
          <div className="card">
            <h3>Recent fetches</h3>
            <ul className="rv-history">
              {s.recent_attempts.map((a, i) => (
                <li key={i}>
                  <div className="what"><Chip tone={TONE[a.outcome] ?? "neutral"}>{a.outcome.replace("_", " ")}</Chip> for {a.for_date}</div>
                  <div className="when">{new Date(a.attempted_at).toLocaleString()} {a.method ? `· ${a.method}` : ""}</div>
                  {a.detail && <div className="note">{a.detail}</div>}
                </li>
              ))}
              {s.recent_attempts.length === 0 && <li className="muted">No attempts yet.</li>}
            </ul>
          </div>
          {hasRole("approver") && (
            <div className="card">
              <h3>Enter a rate by hand</h3>
              <p className="rv-help">For when the RBZ site is down. It is recorded with your name and reason, and shown as entered by hand. Read the ask rate from the RBZ bulletin.</p>
              <form className="inline" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
                <input type="date" value={date} onChange={(e) => setDate(e.target.value)} aria-label="Rate date" />
                <input value={ask} onChange={(e) => setAsk(e.target.value)} inputMode="decimal" placeholder="Ask rate, e.g. 27.2508" aria-label="Ask rate" />
                <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Why (at least 10 characters)" aria-label="Reason" />
                <button disabled={!date || !(Number(ask) > 0) || reason.trim().length < 10 || save.isPending}>Save rate</button>
              </form>
            </div>
          )}
        </>
      )}
    </section>
  );
}
