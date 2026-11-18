import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, hasRole } from "../api";
import { deliverMoney, demoInfo, runScenario, type ScenarioInfo, type ScenarioResult } from "../demo";
import { stateInfo } from "../labels";
import { Icon } from "../components/Icon";
import { useCountUp } from "../lib/useCountUp";
import { InspectLink, Reasons, StateChip } from "../ui";

// The curated order for the guided tour; every other story stays available below it.
const TOUR = ["pay-clear", "pay-waiting", "pay-edited", "kyc-clear", "kyc-mismatch", "kyc-edited"];

const WHO: Record<string, { initials: string; label: string }> = {
  payer: { initials: "P", label: "Payer" },
  reviewer: { initials: "R", label: "Reviewer" },
  approver: { initials: "A", label: "Approver" },
  admin: { initials: "AD", label: "Administrator" },
  system: { initials: "V", label: "Validate" },
};

function Story({ steps }: { steps: ScenarioResult["steps"] }) {
  return (
    <ol className="story">
      {steps.map((s, i) => {
        const w = WHO[s.who] ?? WHO.system;
        return (
          <li key={i} style={{ animationDelay: `${i * 380}ms` }}>
            <span className={`who${s.who === "system" ? " sys" : ""}`} aria-hidden>
              {w.initials}
            </span>
            <span className="txt">
              <small>{w.label}</small>
              {s.text}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

function Outcome({ result, info, onFollow, following }: { result: ScenarioResult; info: ScenarioInfo; onFollow: (f: ScenarioResult["followups"][number]) => void; following: boolean }) {
  const tone = stateInfo(result.state).tone;
  const link =
    result.kind === "payment"
      ? { to: `/claims/${result.ref_id}`, label: "Open the case file" }
      : { to: `/kyc/review?open=${result.ref_id}`, label: result.state === "VERIFIED" ? "See it in the audit list" : "Open the identity check" };
  const toAudit = result.kind === "kyc" && result.state === "VERIFIED";
  return (
    <div className="outcome" aria-live="polite">
      <div className="head">
        <StateChip state={result.state} />
        <span className="headline">{result.headline}</span>
      </div>
      <Story steps={result.steps} />
      <div className="bubble-label">What the {result.kind === "payment" ? "payer" : "person"} is told</div>
      <div className="bubble">
        {result.payer_messages.length
          ? result.payer_messages.map((m, i) => <div key={i}>{m}</div>)
          : tone === "ok"
            ? result.kind === "payment"
              ? "Your payment is confirmed. Thank you."
              : "You are verified."
            : "Your submission is being checked. We will let you know."}
      </div>
      {result.reasons.length > 0 && (
        <>
          <div className="bubble-label">Why the product decided this</div>
          <Reasons codes={result.reasons} />
        </>
      )}
      <div className="learn">
        <b>The point:</b> {info.learn}
      </div>
      <div className="scn-actions">
        {result.followups.map((f) => (
          <button key={f.id} type="button" disabled={following} onClick={() => onFollow(f)}>
            {following ? "Importing…" : f.label}
          </button>
        ))}
        {toAudit ? (
          <InspectLink to="/kyc/review">{link.label}</InspectLink>
        ) : (
          <InspectLink to={link.to}>{link.label}</InspectLink>
        )}
        {result.scenario === "pay-edited" && <InspectLink to="/fraud">See the fraud alert</InspectLink>}
      </div>
    </div>
  );
}

export function ScenarioPanel({ info, compact = false, quiet = false, footer }: { info: ScenarioInfo; compact?: boolean; quiet?: boolean; footer?: React.ReactNode }) {
  const [result, setResult] = useState<ScenarioResult | null>(null);
  const run = useMutation({ mutationFn: () => runScenario(info.id), onSuccess: setResult });
  const follow = useMutation({ mutationFn: deliverMoney, onSuccess: setResult });
  return (
    <div className="card scn">
      <div className="scn-head">
        <div className="tag">{info.group === "payments" ? "Payments" : "Identity"}</div>
        <h2>{info.title}</h2>
        <p className="muted">{info.pitch}</p>
      </div>
      <div className="scn-body">
        {(!result || !compact) && (
          <div className="scn-actions">
            {/* one run button: it starts the story, and once there is an outcome it replays it */}
            <button
              type="button"
              className={result ? "secondary" : quiet ? "secondary lg" : "lg"}
              disabled={run.isPending}
              onClick={() => {
                if (result) {
                  setResult(null);
                  run.reset();
                } else {
                  run.mutate();
                }
              }}
            >
              {run.isPending ? "Running…" : result ? <><Icon name="refresh" size={14} /> Run again</> : <><Icon name="play" size={14} /> Run this story</>}
            </button>
            {run.isPending && <span className="muted small">Acting as the payer, then the system…</span>}
            {run.isError && <span className="error">{(run.error as Error).message}</span>}
          </div>
        )}
      </div>
      {result && <Outcome result={result} info={info} following={follow.isPending} onFollow={(f) => follow.mutate(f.params)} />}
      {follow.isError && <p className="error" style={{ margin: 12 }}>{(follow.error as Error).message}</p>}
      {footer}
    </div>
  );
}

function HeroArt() {
  return (
    <svg className="hero-art" viewBox="0 0 300 320" aria-hidden focusable="false">
      <defs>
        <linearGradient id="ha-beam" x1="0" x2="1">
          <stop offset="0" stopColor="#429ebd" stopOpacity="0" />
          <stop offset="0.5" stopColor="#429ebd" stopOpacity="0.85" />
          <stop offset="1" stopColor="#429ebd" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="ha-shield" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#429ebd" />
          <stop offset="1" stopColor="#053f5c" />
        </linearGradient>
        <clipPath id="ha-clip"><rect x="62" y="52" width="136" height="176" rx="14" /></clipPath>
      </defs>
      <circle className="ha-blob" cx="150" cy="160" r="128" />
      <circle className="ha-orbit" cx="150" cy="160" r="142" />
      <g className="ha-float ha-f1">
        <rect className="ha-paper" x="62" y="52" width="136" height="176" rx="14" />
        <g clipPath="url(#ha-clip)">
          <rect className="ha-line" x="82" y="82" width="70" height="8" rx="4" />
          <rect className="ha-line" x="82" y="104" width="96" height="6" rx="3" style={{ animationDelay: "120ms" }} />
          <rect className="ha-line" x="82" y="120" width="84" height="6" rx="3" style={{ animationDelay: "220ms" }} />
          <rect className="ha-line" x="82" y="136" width="90" height="6" rx="3" style={{ animationDelay: "320ms" }} />
          <rect className="ha-line amber" x="82" y="166" width="52" height="10" rx="5" style={{ animationDelay: "420ms" }} />
          <rect className="ha-beam" x="62" y="52" width="136" height="26" fill="url(#ha-beam)" />
        </g>
      </g>
      <g className="ha-float ha-f2">
        <path className="ha-shield" d="M196 150 l44 16 v36 c0 24 -18 40 -44 52 c-26 -12 -44 -28 -44 -52 v-36 z" fill="url(#ha-shield)" />
        <path className="ha-check" d="M174 206 l16 16 l32 -34" />
      </g>
      <g className="ha-float ha-f3"><circle className="ha-coin" cx="240" cy="64" r="17" /><text x="240" y="70" textAnchor="middle" className="ha-coin-t">$</text></g>
      <g className="ha-float ha-f4"><circle className="ha-ring" cx="44" cy="206" r="11" /></g>
      <g className="ha-float ha-f2"><circle cx="262" cy="130" r="5" fill="#429ebd" /><circle cx="30" cy="110" r="4" fill="#f7ad19" /><circle cx="110" cy="286" r="5" fill="#f27f0c" /></g>
      <g className="ha-float ha-f4">
        <circle cx="86" cy="262" r="20" fill="#9fe7f5" stroke="#429ebd" strokeWidth="2" />
        <circle cx="86" cy="256" r="6.5" fill="#053f5c" />
        <path d="M73 274 c2 -9 24 -9 26 0" fill="#053f5c" />
      </g>
    </svg>
  );
}

function Figure({ n, label }: { n: number | undefined; label: string }) {
  const shown = useCountUp(n);
  return (
    <div className="stat">
      <div className="n">{shown ?? "–"}</div>
      <div className="l">{label}</div>
    </div>
  );
}

function Stats() {
  const queue = useQuery({ queryKey: ["home-queue"], queryFn: () => api<unknown[]>("/review/queue"), enabled: hasRole("reviewer"), refetchInterval: 15000 });
  const kyc = useQuery({ queryKey: ["home-kyc"], queryFn: () => api<unknown[]>("/kyc/review/queue"), enabled: hasRole("reviewer"), refetchInterval: 15000 });
  const auto = useQuery({ queryKey: ["home-auto"], queryFn: () => api<{ summary: { approved: number } }>("/review/auto-approved"), enabled: hasRole("reviewer"), refetchInterval: 15000 });
  const autoKyc = useQuery({ queryKey: ["home-autokyc"], queryFn: () => api<{ summary: { verified: number } }>("/kyc/review/auto-verified"), enabled: hasRole("reviewer"), refetchInterval: 15000 });
  if (!hasRole("reviewer")) return null;
  const items = [
    { n: auto.data?.summary.approved, l: "payments approved by the rules" },
    { n: autoKyc.data?.summary.verified, l: "identities verified by the rules" },
    { n: queue.data?.length, l: "payments waiting for a person" },
    { n: kyc.data?.length, l: "identity checks waiting for a person" },
  ];
  return (
    <div className="stats" aria-label="Live numbers">
      {items.map((s) => (
        <Figure key={s.l} n={s.n} label={s.l} />
      ))}
    </div>
  );
}

// Two sample case files, written as ledger rows: what was read, what it was matched to, what was decided.
// Illustrative values; the reason codes and states are the real ones the product uses.
const CASES: { title: string; state: string; rows: [string, string, string][]; reasons: string[] }[] = [
  {
    title: "Clear case: approved by the rules",
    state: "APPROVED",
    rows: [
      ["Amount", "120.00 USD", "120.00 USD"],
      ["Reference", "TX-48213", "TX-48213"],
      ["Paid to", "Greenfield School", "Greenfield School"],
    ],
    reasons: ["AUTO_APPROVED"],
  },
  {
    title: "Doubtful case: sent to a person",
    state: "PENDING_REVIEW",
    rows: [
      ["Amount", "120.00 USD", "100.00 USD"],
      ["Reference", "TX-48214", "TX-48214"],
      ["Paid to", "Greenfield School", "Greenfield School"],
    ],
    reasons: ["AMOUNT_MISMATCH"],
  },
];

function CaseFiles() {
  return (
    <div className="casefiles">
      {CASES.map((c) => (
        <article className="casefile" key={c.title}>
          <header>
            <h3>{c.title}</h3>
            <StateChip state={c.state} />
          </header>
          <table>
            <thead>
              <tr><th /><th>Receipt says</th><th>Bank record says</th></tr>
            </thead>
            <tbody>
              {c.rows.map(([k, a, b]) => (
                <tr key={k} className={a === b ? "" : "differs"}>
                  <th scope="row">{k}</th>
                  <td className="data">{a}</td>
                  <td className="data">{b}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <Reasons codes={c.reasons} />
        </article>
      ))}
    </div>
  );
}

export default function Home() {
  const demo = demoInfo();
  const [step, setStep] = useState(0);
  const [seen, setSeen] = useState<Set<number>>(new Set());
  const [group, setGroup] = useState<"all" | "payments" | "identity">("all");
  const scenarios = demo?.scenarios ?? [];
  const byId = new Map(scenarios.map((s) => [s.id, s]));
  const tour = TOUR.map((id) => byId.get(id)).filter(Boolean) as ScenarioInfo[];
  const more = scenarios.filter((s) => !TOUR.includes(s.id) && (group === "all" || s.group === group));
  const current = tour[step];

  const go = (i: number) => {
    setStep(i);
    setSeen((s) => new Set(s).add(step));
    document.getElementById("tour")?.scrollIntoView({ block: "start" });
  };

  return (
    <div>
      <section className="hero2">
        <HeroArt />
        <h1>Match every payment proof to the bank record. Check every ID against its holder.</h1>
        <p>
          Validate reads the receipt or document and compares it with the bank credit or the ID. When every rule
          passes it approves; when one fails, a reviewer gets the case with the exact reason.
        </p>
        <div className="cta">
          <button
            type="button"
            className="btn lg"
            onClick={() => document.getElementById(demo ? "tour" : "decisions")?.scrollIntoView({ behavior: "smooth" })}
          >
            {demo ? "Run a live case" : "See how a case is decided"}
          </button>
          <Link className="btn secondary lg" to="/verify">Try it on your own payment</Link>
        </div>
        <ol className="how-steps" aria-label="How it works">
          <li><b>It reads</b>Two readers pull the facts from the picture.</li>
          <li><b>It checks</b>The money, the rules and the documents must agree.</li>
          <li><b>A person decides</b>Anything doubtful is never decided by a machine.</li>
        </ol>
      </section>

      <Stats />

      {demo ? (
        <>
          <div className="section-title" id="tour">
            <h2>Live cases</h2>
            <span className="muted small">You are the administrator. Each case runs the real product end to end; use the menu at the top right to switch to the payer or reviewer.</span>
          </div>
          {current && (
            <div className="tour">
              <ol className="tour-steps" aria-label="Tour steps">
                {tour.map((t, i) => (
                  <li key={t.id}>
                    <button type="button" className={`tour-step${i === step ? " on" : ""}${seen.has(i) ? " done" : ""}`} onClick={() => go(i)} aria-current={i === step}>
                      <span className="num">{seen.has(i) ? <Icon name="check" size={13} /> : i + 1}</span>
                      <span>
                        {t.title}
                        <small>{t.group === "payments" ? "Payments" : "Identity"}</small>
                      </span>
                    </button>
                  </li>
                ))}
              </ol>
              <div>
                <ScenarioPanel key={current.id} info={current} />
                {step < tour.length - 1 && (
                  <div className="tour-nav">
                    <button type="button" onClick={() => go(step + 1)}>Next story</button>
                  </div>
                )}
              </div>
            </div>
          )}

          <div className="section-title">
            <h2>More stories</h2>
            <div className="seg" role="tablist" aria-label="Filter stories">
              {(["all", "payments", "identity"] as const).map((g) => (
                <button key={g} type="button" role="tab" aria-selected={group === g} className={group === g ? "on" : ""} onClick={() => setGroup(g)}>
                  {g === "all" ? "All" : g === "payments" ? "Payments" : "Identity"}
                </button>
              ))}
            </div>
          </div>
          <div className="grid reveal">
            {more.map((s) => (
              <ScenarioPanel key={s.id} info={s} quiet />
            ))}
          </div>
        </>
      ) : (
        <div className="card">
          <h2>Welcome</h2>
          <p className="muted">This build has no demo scenarios. Use the menu to verify a payment or an identity document.</p>
        </div>
      )}

      <section className="section" id="decisions">
        <h2>How a case is decided</h2>
        <p className="muted">
          A receipt can be edited in seconds, so it never settles anything alone: the bank record does. Approval is a
          short list of fixed checks. It never rejects; a failed check sends the case to a person. Every decision is
          kept on record, and a sample of automatic ones is re-checked by a person.
        </p>
      </section>
      <CaseFiles />
      {demo && (
        <p className="muted small" style={{ marginTop: 28 }}>
          In this demo the readers and face matcher are simulated and understand only the sample documents it
          generates. A real deployment uses a vision model and a face model you supply.
        </p>
      )}
    </div>
  );
}
