import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, money } from "../api";
import { Loading, PageHeader } from "../ui";
import { CardCell, CardTable } from "../components/CardTable";
import "./review.css";

type Card = {
  window: { start: string; end: string };
  claims_received: number;
  waiting_for_a_person_now: number;
  cleared_by_rules: number;
  approved_by_a_person: number;
  rejected_by_a_person: number;
  duplicates_held: number;
  fakes_confirmed: number;
  median_minutes_to_decision: number | null;
  estimated_staff_minutes_saved: number;
  estimate_note: string;
  money_confirmed_by_day: { date: string; currency: string; minor: number }[];
  agreement_with_reviewers: { proposals: number; scored: number };
};

const iso = (d: Date) => d.toISOString().slice(0, 10);

function Tile({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <div className="card rv-tile" title={hint}>
      <div className="rv-tile-value">{value}</div>
      <div className="muted small">{label}</div>
    </div>
  );
}

/** The numbers that decide whether a pilot pays for itself. */
export default function Scorecard() {
  const today = new Date();
  const [start, setStart] = useState(iso(new Date(today.getTime() - 13 * 86400000)));
  const [end, setEnd] = useState(iso(today));
  const q = useQuery({ queryKey: ["pilot", start, end], queryFn: () => api<Card>(`/admin/pilot-scorecard?start=${start}&end=${end}`) });
  const c = q.data;
  const share = c && c.cleared_by_rules + c.approved_by_a_person > 0 ? Math.round((c.cleared_by_rules / (c.cleared_by_rules + c.approved_by_a_person)) * 100) : null;
  return (
    <section className="rv">
      <PageHeader title="Pilot scorecard" sub="What Validate did in this window. Staff time saved is an estimate until real timings are measured." />
      <div className="inline" style={{ marginBottom: 12 }}>
        <label className="small">From <input type="date" value={start} onChange={(e) => setStart(e.target.value)} /></label>
        <label className="small">To <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} /></label>
      </div>
      {q.isLoading && <Loading lines={4} />}
      {q.error && <p className="error">{(q.error as Error).message}</p>}
      {c && (
        <>
          <div className="rv-tiles">
            <Tile label="Claims received" value={c.claims_received} />
            <Tile label="Cleared by the rules" value={c.cleared_by_rules} hint="Approved automatically under the written rules" />
            <Tile label="Approved by a person" value={c.approved_by_a_person} />
            <Tile label="Share cleared by rules" value={share === null ? "—" : `${share}%`} />
            <Tile label="Median minutes to decision" value={c.median_minutes_to_decision ?? "—"} />
            <Tile label="Duplicates held" value={c.duplicates_held} />
            <Tile label="Fakes confirmed" value={c.fakes_confirmed} />
            <Tile label="Waiting for a person now" value={c.waiting_for_a_person_now} />
            <Tile label="Staff minutes saved (estimate)" value={c.estimated_staff_minutes_saved} hint={c.estimate_note} />
          </div>
          <p className="muted small">{c.estimate_note}</p>
          <div className="card">
            <h3>Money confirmed per day</h3>
            <CardTable caption="Money confirmed per day">
              <thead><tr><th>Date</th><th>Currency</th><th className="num">Confirmed</th></tr></thead>
              <tbody>
                {c.money_confirmed_by_day.map((m) => (
                  <tr key={`${m.date}-${m.currency}`}>
                    <CardCell label="Date">{m.date}</CardCell>
                    <CardCell label="Currency">{m.currency}</CardCell>
                    <CardCell label="Confirmed" className="num">{money(m.minor, m.currency)}</CardCell>
                  </tr>
                ))}
                {c.money_confirmed_by_day.length === 0 && <tr><CardCell label="" wide colSpan={3} className="muted">No money confirmed in this window.</CardCell></tr>}
              </tbody>
            </CardTable>
          </div>
        </>
      )}
    </section>
  );
}
