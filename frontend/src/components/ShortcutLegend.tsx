import { useEffect, useState } from "react";
import { Dialog } from "./Dialog";

export type Shortcut = [keys: string, what: string];

/** A small "?" help: lists a page's keyboard shortcuts. Opens with the ? key as well as a button. */
export function ShortcutLegend({ title, shortcuts }: { title: string; shortcuts: Shortcut[] }) {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).tagName.match(/INPUT|TEXTAREA|SELECT/)) return;
      if (e.key === "?") {
        e.preventDefault();
        setOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  return (
    <>
      <button type="button" className="ghost small" onClick={() => setOpen(true)} aria-label="Keyboard shortcuts" title="Keyboard shortcuts (?)">
        ⌨ Shortcuts
      </button>
      {open && (
        <Dialog title={title} onClose={() => setOpen(false)}>
          <dl className="shortcuts">
            {shortcuts.map(([keys, what]) => (
              <div key={keys}>
                <dt>
                  {keys.split(" ").map((k) => (
                    <kbd key={k}>{k}</kbd>
                  ))}
                </dt>
                <dd>{what}</dd>
              </div>
            ))}
          </dl>
          <div className="dialog-actions">
            <button type="button" className="ghost" onClick={() => setOpen(false)}>
              Close
            </button>
          </div>
        </Dialog>
      )}
    </>
  );
}
