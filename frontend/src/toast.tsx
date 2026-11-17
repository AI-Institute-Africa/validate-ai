import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { UNDO_SECONDS, cancel, tick, type Delayed } from "./lib/undo";

type Kind = "ok" | "err" | "info";
type Toast = { id: number; kind: Kind; msg: string };

const ToastCtx = createContext<(kind: Kind, msg: string) => void>(() => {});

export const useToast = () => useContext(ToastCtx);

// Schedule an action that is sent after a short countdown, with an Undo button. Used for actions that
// cannot be taken back once sent. Survives moving between pages; closing the tab cancels it (and warns).
type Schedule = (label: string, run: () => void | Promise<void>, seconds?: number) => void;
const UndoCtx = createContext<Schedule>(() => {});
export const useUndo = () => useContext(UndoCtx);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);

  const push = useCallback((kind: Kind, msg: string) => {
    const id = nextId.current++;
    setToasts((t) => [...t, { id, kind, msg }]);
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4500);
  }, []);

  const [delayed, setDelayed] = useState<Delayed[]>([]);
  const ref = useRef<Delayed[]>([]);
  const set = (next: Delayed[]) => {
    ref.current = next;
    setDelayed(next);
  };
  const schedule = useCallback<Schedule>((label, run, seconds = UNDO_SECONDS) => {
    set([...ref.current, { id: nextId.current++, label, left: seconds, run }]);
  }, []);

  useEffect(() => {
    if (!delayed.length) return;
    const timer = window.setInterval(() => {
      const { keep, due } = tick(ref.current);
      set(keep);
      for (const d of due) {
        Promise.resolve(d.run()).catch((e: Error) => push("err", e.message || "That did not go through."));
      }
    }, 1000);
    const warn = (e: BeforeUnloadEvent) => e.preventDefault(); // closing now would cancel the action
    window.addEventListener("beforeunload", warn);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("beforeunload", warn);
    };
  }, [delayed.length > 0, push]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <ToastCtx.Provider value={push}>
      <UndoCtx.Provider value={schedule}>
        {children}
        <div className="toasts" role="status" aria-live="polite">
          {toasts.map((t) => (
            <div key={t.id} className={`toast ${t.kind}`}>
              {t.msg}
            </div>
          ))}
          {delayed.map((d) => (
            <div key={d.id} className="toast info undo">
              <span>
                {d.label} in {d.left} s
              </span>
              <button type="button" className="small" onClick={() => set(cancel(ref.current, d.id))}>
                Undo
              </button>
            </div>
          ))}
        </div>
      </UndoCtx.Provider>
    </ToastCtx.Provider>
  );
}
