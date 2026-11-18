import { NavLink } from "react-router-dom";

/** Allocating money has two modes, one credit to one invoice or one credit across many. A switch, not a second page link. */
export function CreditsModes() {
  return (
    <nav className="rv-tabs" aria-label="Allocation mode">
      <NavLink to="/credits" end className="rv-tab">Allocate credits</NavLink>
      <NavLink to="/credits/bulk" className="rv-tab">Split one payment across invoices</NavLink>
    </nav>
  );
}
