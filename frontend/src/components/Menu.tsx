import { useEffect, useRef, useState, type ReactNode } from "react";

export type MenuItem = { label: string; onSelect: () => void; hidden?: boolean; disabled?: boolean };

/** A small action menu: one button that opens a list. Esc and a click outside close it, like the persona menu. */
export function Menu({ label, items, up = false, className = "" }: { label: ReactNode; items: MenuItem[]; up?: boolean; className?: string }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => !box.current?.contains(e.target as Node) && setOpen(false);
    const esc = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setOpen(false);
      trigger.current?.focus(); // keyboard users land back on the button that opened the menu
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);
  const shown = items.filter((i) => !i.hidden);
  if (!shown.length) return null;
  return (
    <div className={`menu ${className}`} ref={box}>
      <button ref={trigger} type="button" className="secondary" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        {label} <span className="small" aria-hidden>▾</span>
      </button>
      {open && (
        <div className={`menu-list${up ? " up" : ""}`} role="menu">
          {shown.map((i) => (
            <button
              key={i.label}
              type="button"
              role="menuitem"
              disabled={i.disabled}
              onClick={() => {
                setOpen(false);
                i.onSelect();
              }}
            >
              {i.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
