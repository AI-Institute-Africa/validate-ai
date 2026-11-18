import { Suspense, lazy } from "react";
import { NavLink, Navigate, useParams } from "react-router-dom";

// One home for the admin views that are looked at occasionally. Each tab is the existing page, unchanged.
const Exposure = lazy(() => import("./Exposure"));
const Scorecard = lazy(() => import("./Scorecard"));
const Replay = lazy(() => import("./Replay"));
const Compliance = lazy(() => import("./Compliance"));
const Fx = lazy(() => import("./Fx"));

const TABS = [
  { key: "exposure", label: "Exposure", Page: Exposure },
  { key: "scorecard", label: "Pilot scorecard", Page: Scorecard },
  { key: "replay", label: "Replay & accuracy", Page: Replay },
  { key: "fx", label: "Exchange rate", Page: Fx },
  { key: "compliance", label: "Compliance", Page: Compliance },
] as const;

export default function Insights() {
  const { tab } = useParams();
  const current = TABS.find((t) => t.key === tab);
  if (!current) return <Navigate to={`/insights/${TABS[0].key}`} replace />;
  const { Page } = current;
  return (
    <div>
      <nav className="rv-tabs" aria-label="Insights">
        {TABS.map((t) => (
          <NavLink key={t.key} to={`/insights/${t.key}`} className="rv-tab" aria-current={t.key === current.key ? "page" : undefined}>
            {t.label}
          </NavLink>
        ))}
      </nav>
      <Suspense fallback={<div className="spinner" role="status" aria-label="Loading" />}>
        <Page />
      </Suspense>
    </div>
  );
}
