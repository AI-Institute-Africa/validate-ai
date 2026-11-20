import { useEffect, useRef, type RefObject } from "react";

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/** Move focus into an open panel, keep Tab inside it, close on Escape, and return focus to the
 *  opener on close. Used by the mobile drawer and by dialogs. */
export function useFocusTrap(
  active: boolean,
  ref: RefObject<HTMLElement>,
  onClose: () => void,
  openerRef?: RefObject<HTMLElement>,
): void {
  const close = useRef(onClose);
  close.current = onClose;

  useEffect(() => {
    if (!active) return;
    const panel = ref.current;
    if (!panel) return;
    const opener = openerRef?.current ?? (document.activeElement as HTMLElement | null);
    const items = () => Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE));

    (items()[0] ?? panel).focus();

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        close.current();
        return;
      }
      if (e.key !== "Tab") return;
      const focusables = items();
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (!first) {
        e.preventDefault();
        panel.focus();
      } else if (e.shiftKey && (document.activeElement === first || !panel.contains(document.activeElement))) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && (document.activeElement === last || !panel.contains(document.activeElement))) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      if (opener?.isConnected) opener.focus();
    };
  }, [active, ref, openerRef]);
}
