import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, Claim, money } from "../api";
import { reasonText, type Tone } from "../labels";
import { Chip, EmptyState, Loading, PageHeader, StateChip } from "../ui";
import { bucketOf, slaOf, SLA_MINUTES, type Bucket } from "../lib/triage";
import { ariaSort, DEFAULT_SORT, nextSort, sortClaims, type Sort, type SortKey } from "../lib/sortClaims";
import { ShortcutLegend } from "../components/ShortcutLegend";
import { pruneSelection, toggle, toggleAll } from "../lib/bulk";
import { BulkBar } from "./QueueBulk";
import { RiskBadge } from "./Fraud";
import "./review.css";

// [state filter value, label]. The label says what the reviewer should do, not what the code is called.
const FILTERS: [string, string][] = [
  ["", "Everything waiting"],
  ["FINANCIALLY_CONFIRMED", "Money confirmed"],
  ["PENDING_REVIEW", "Needs a person"],
  ["AWAITING_FINANCIAL_CONFIRMATION", "Waiting for the money"],
  ["DUPLICATE_HOLD", "Possible duplicates"],
  ["DOCUMENT_VERIFIED", "Document read"],
];

const TIERS: Record<string, { label: string; tone: Tone; hint: string }> = {
  GREEN: { label: "Green", tone: "ok", hint: "Green: evidence is strong and nothing is wrong. Quick to approve." },
  AMBER: { label: "Amber", tone: "warn", hint: "Amber: something is missing or unusual. Look before approving." },
  RED: { label: "Red", tone: "bad", hint: "Red: a hard stop such as a duplicate or wrong amount. Do not approve as it stands." },
};

const EVIDENCE: Record<string, { label: string; hint: string }> = {
  E0: { label: "Claim only", hint: "E0: the payer says they paid; nothing backs it up yet." },
  E1: { label: "Receipt only", hint: "E1: the receipt reads consistently, but a receipt alone is never proof." },
  E2: { label: "Alert confirmed", hint: "E2: backed by a payment alert or an attested manual record." },
  E3: { label: "Bank confirmed", hint: "E3: matched to a settled statement line or gateway record." },
};

export function TierBadge({ tier }: { tier: string | null }) {
  if (!tier) return null;
  const t = TIERS[tier.toUpperCase()] ?? { label: tier, tone: "neutral" as Tone, hint: "" };
  return <Chip tone={t.tone} title={t.hint}>{t.label}</Chip>;
}

export function StateBadge({ state }: { state: string }) {
  return <StateChip state={state} />;
}

export function EvidenceChip({ tier, compact }: { tier: string; compact?: boolean }) {
  const e = EVIDENCE[tier];
  return (
    <Chip tone={tier === "E3" || tier === "E2" ? "ok" : "neutral"} title={e?.hint ?? tier}>
      {e ? e.label : tier}{!compact && <span className="rv-code">{tier}</span>}
    </Chip>
  );
}

// "5 min ago", "3 h ago", "2 d ago". Exact time stays in the title.
export function agoText(iso: string): string {
  const mins = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
  if (!(mins >= 1)) return "just now";
  if (mins < 60) return `${mins} min ago`;
  if (mins < 1440) return `${Math.floor(mins / 60)} h ago`;
  return `${Math.floor(mins / 1440)} d ago`;
}

const SORT_KEY = "validate-queue-sort";
export function loadSort(): Sort {
  try {
    const s = JSON.parse(sessionStorage.getItem(SORT_KEY) ?? "null");
    if (s && typeof s.key === "string" && (s.dir === "asc" || s.dir === "desc")) return s;
  } catch {
    /* no storage: use the default */
  }
  return DEFAULT_SORT;
}

const SLA_LABEL = ["", `${SLA_MINUTES[0] / 60} h+`, `${SLA_MINUTES[1] / 60} h+`, `${SLA_MINUTES[2] / 60} h+`];

function SortBtn({ k, label, sort, onSort }: { k: SortKey; label: string; sort: Sort; onSort: (k: SortKey) => void }) {
  const active = sort.key === k;
  return (
    <button type="button" className="rv-sort" data-active={active} onClick={() => onSort(k)} title={`Sort by ${label.toLowerCase()}`}>
      {label}
      <span aria-hidden>{active ? (sort.dir === "asc" ? "▲" : "▼") : ""}</span>
    </button>
  );
}

export default function Queue() {
  const nav = useNavigate();
  const [sort, setSort] = useState<Sort>(loadSort);
  const [cursor, setCursor] = useState(0);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const chooseSort = (key: SortKey) => {
    const next = nextSort(sort, key);
    setSort(next);
    try {
      sessionStorage.setItem(SORT_KEY, JSON.stringify(next));
    } catch {
      /* ignore */
    }
  };
  const [state, setState] = useState("");
  const [channel, setChannel] = useState("");
  const [bucket, setBucket] = useState<Bucket>("needs_review");
  const params = new URLSearchParams();
  if (state) params.set("state", state);
  if (channel.trim()) params.set("channel", channel.trim());
  const q = useQuery({
    queryKey: ["queue", state, channel],
    queryFn: () => api<Claim[]>(`/review/queue?${params}`),
    refetchInterval: 15000,
  });
  const filtered = !!state || !!channel.trim();
  const all = q.data;
  const counts = {
    needs_review: all?.filter((c) => bucketOf(c) === "needs_review").length ?? 0,
    flagged: all?.filter((c) => bucketOf(c) === "flagged").length ?? 0,
  };
  const rows = all && sortClaims(all.filter((c) => bucketOf(c) === bucket), sort);

  // j / k move through the rows, Enter opens the one in focus
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).tagName.match(/INPUT|TEXTAREA|SELECT|BUTTON|A/)) return;
      if (!rows?.length) return;
      if (e.key === "j" || e.key === "ArrowDown" || e.key === "k" || e.key === "ArrowUp") {
        e.preventDefault();
        const step = e.key === "j" || e.key === "ArrowDown" ? 1 : -1;
        const next = Math.min(rows.length - 1, Math.max(0, cursor + step));
        setCursor(next);
        document.querySelector<HTMLElement>(`tr[data-row="${next}"]`)?.focus();
      } else if (e.key === "Enter" && rows[cursor] && document.activeElement?.closest("tr[data-row]")) {
        nav(`/claims/${rows[cursor].claim_id}`);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [rows, cursor, nav]);
  useEffect(() => setCursor(0), [bucket, state, channel]);
  // a ticked claim that is no longer listed (filtered out, or decided elsewhere) is dropped from the selection
  const visibleIds = (rows ?? []).map((c) => c.claim_id).join(",");
  useEffect(() => {
    setSelected((s) => (s.size ? pruneSelection(s, visibleIds ? visibleIds.split(",") : []) : s));
  }, [visibleIds]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).tagName.match(/INPUT|TEXTAREA|SELECT|BUTTON|A/) && !(e.target as HTMLElement).closest("tr[data-row]")) return;
      if (e.key === "x" && rows?.[cursor]) {
        e.preventDefault();
        setSelected((s) => toggle(s, rows[cursor].claim_id));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [rows, cursor]);
  const chosen = (rows ?? []).filter((c) => selected.has(c.claim_id));

  return (
    <section className="rv" id="rv-panel">
      <PageHeader
        title="Review queue"
        sub="Claims waiting for a person. Click a column title to sort. Click a row, or use j and k then Enter, to open the receipt, the matching bank credit and the decision."
        actions={<ShortcutLegend title="Queue shortcuts" shortcuts={[["j ↓", "Next claim"], ["k ↑", "Previous claim"], ["x", "Tick or untick the claim in focus"], ["Enter", "Open the claim in focus"], ["?", "Show this list"]]} />}
      />
      <div
        className="rv-tabs"
        role="tablist"
        aria-label="Triage"
        onKeyDown={(e) => {
          // arrow keys move between the two tabs, as users of tab widgets expect
          if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
            const next = bucket === "needs_review" ? "flagged" : "needs_review";
            setBucket(next);
            requestAnimationFrame(() =>
              document.querySelector<HTMLButtonElement>(`[role=tab][data-bucket=${next}]`)?.focus(),
            );
          }
        }}
      >
        <button type="button" role="tab" data-bucket="needs_review" aria-controls="rv-panel" tabIndex={bucket === "needs_review" ? 0 : -1} aria-selected={bucket === "needs_review"} className="rv-tab" onClick={() => setBucket("needs_review")}>
          Needs review <span className="rv-tabcount">{counts.needs_review}</span>
        </button>
        <button type="button" role="tab" data-bucket="flagged" aria-controls="rv-panel" tabIndex={bucket === "flagged" ? 0 : -1} aria-selected={bucket === "flagged"} className="rv-tab flagged" onClick={() => setBucket("flagged")}>
          Flagged / high risk <span className="rv-tabcount">{counts.flagged}</span>
        </button>
        <Link className="rv-tab" to="/auto">Auto-verified (audit) →</Link>
      </div>
      <div className="rv-filters">
        <div className="rv-pills" role="group" aria-label="Show claims">
          {FILTERS.map(([v, label]) => (
            <button key={v} type="button" className="rv-pill" aria-pressed={state === v} onClick={() => setState(v)}>
              {label}
            </button>
          ))}
        </div>
      </div>
      <div className="rv-filters">
        <input
          className="rv-search"
          type="search"
          placeholder="Channel, e.g. whatsapp"
          aria-label="Filter by channel"
          value={channel}
          onChange={(e) => setChannel(e.target.value)}
        />
        {filtered && (
          <button type="button" className="ghost small" onClick={() => { setState(""); setChannel(""); }}>
            Clear filters
          </button>
        )}
        <span className="rv-count">
          {rows ? `${rows.length} claim${rows.length === 1 ? "" : "s"}` : ""}
        </span>
      </div>
      {q.error && <p className="error">{(q.error as Error).message}</p>}
      {q.isLoading && <Loading lines={5} />}
      {rows?.length === 0 && (
        filtered ? (
          <EmptyState icon="🔍" title="Nothing matches these filters" action={<button type="button" className="secondary" onClick={() => { setState(""); setChannel(""); }}>Show everything</button>}>
            Try a different status or clear the channel box.
          </EmptyState>
        ) : (
          <EmptyState icon="✓" title="The queue is clear" action={<Link className="btn secondary" to="/">Go to Home</Link>}>
            Nothing needs a person right now. Run a story from Home to fill this.
          </EmptyState>
        )
      )}
      {!!rows?.length && (
        <div className="card rv-flush">
          <div className="table-wrap">
            <table className="rv-cards">
              <thead>
                <tr>
                  <th className="sel">
                    <input
                      type="checkbox"
                      aria-label="Select all listed claims"
                      checked={rows.length > 0 && rows.every((c) => selected.has(c.claim_id))}
                      onChange={() => setSelected(toggleAll(selected, rows.map((c) => c.claim_id)))}
                    />
                  </th>
                  <th aria-sort={ariaSort(sort, "waiting")}><SortBtn k="waiting" label="Waiting" sort={sort} onSort={chooseSort} /></th>
                  <th aria-sort={ariaSort(sort, "status")}><SortBtn k="status" label="Status" sort={sort} onSort={chooseSort} /></th>
                  <th>Claimant</th>
                  <th className="num" aria-sort={ariaSort(sort, "declared")}><SortBtn k="declared" label="Declared" sort={sort} onSort={chooseSort} /></th>
                  <th>Evidence</th>
                  <th title="Level: how careful to be. Risk: fake-receipt signals.">
                    <SortBtn k="level" label="Level" sort={sort} onSort={chooseSort} /> and <SortBtn k="risk" label="risk" sort={sort} onSort={chooseSort} />
                  </th>
                  <th>Why it is here</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((c, i) => (
                  <tr
                    key={c.claim_id}
                    data-row={i}
                    tabIndex={i === cursor ? 0 : -1}
                    className={`rv-click${i === cursor ? " cursor" : ""}`}
                    onFocus={() => setCursor(i)}
                    onClick={(e) => { if (!(e.target as HTMLElement).closest("a,button,input")) nav(`/claims/${c.claim_id}`); }}
                  >
                    <td className="sel" data-label="Select">
                      <input
                        type="checkbox"
                        aria-label={`Select ${c.claimant_ref}`}
                        checked={selected.has(c.claim_id)}
                        onChange={() => setSelected(toggle(selected, c.claim_id))}
                      />
                    </td>
                    <td data-label="Waiting">
                      <Link className="rv-age" to={`/claims/${c.claim_id}`} title={new Date(c.created_at).toLocaleString()}>
                        {agoText(c.created_at)}
                      </Link>
                      {slaOf(c.created_at, Date.now()).level > 0 && (
                        <Chip tone={slaOf(c.created_at, Date.now()).tone} title={`Waiting longer than ${SLA_LABEL[slaOf(c.created_at, Date.now()).level].replace("+", "")}. Reminders go out at ${SLA_MINUTES.map((m) => m / 60 + " h").join(", ")}.`}>
                          {SLA_LABEL[slaOf(c.created_at, Date.now()).level]}
                        </Chip>
                      )}
                    </td>
                    <td data-label="Status"><StateChip state={c.state} /></td>
                    <td className="nowrap" data-label="Claimant">
                      {c.claimant_ref}
                      <span className="rv-sub">{c.channel}</span>
                    </td>
                    <td className="num" data-label="Declared">{money(c.declared_amount_minor, c.declared_currency)}</td>
                    <td data-label="Evidence"><EvidenceChip tier={c.evidence_tier} compact /></td>
                    <td data-label="Level and risk"><span className="rv-chips"><TierBadge tier={c.approval_tier} /><RiskBadge level={c.risk_level} score={c.risk_score} /></span></td>
                    <td className="rv-why" data-label="Why it is here">
                      {c.reason_codes.length === 0 ? (
                        <span className="muted">No problems recorded</span>
                      ) : (
                        <>
                          {reasonText(c.reason_codes[0])}
                          <div className="rv-codes">
                            {c.reason_codes.map((r) => (
                              <code key={r} className="rv-code" title={reasonText(r)}>{r}</code>
                            ))}
                          </div>
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      <BulkBar selected={chosen} onClear={() => setSelected(new Set())} />
    </section>
  );
}
