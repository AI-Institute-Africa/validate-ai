import { useRef, type ReactNode } from "react";
import { useFocusTrap } from "../lib/focusTrap";

/** Small modal: Esc closes, focus moves in on open and back to the opener on close. */
export function Dialog({ title, onClose, children, wide }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  useFocusTrap(true, ref, onClose);
  return (
    <div className="overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className={`modal${wide ? " wide" : ""}`} role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} ref={ref}>
        <h3>{title}</h3>
        {children}
      </div>
    </div>
  );
}
