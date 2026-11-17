// Sends a claim upload with progress, and keeps it safe if the connection fails: it is saved on this
// device and sent again with the same Idempotency-Key, on a backoff and whenever the phone is back online.

import { useCallback, useEffect, useRef, useState } from "react";
import { postWithProgress, type Claim } from "../api";
import { backoffMs, cannotQueue, deviceStore, isRetryable, type Pending, type Store } from "./outbox";

export type SenderState =
  | { phase: "idle" }
  | { phase: "sending"; progress: number; key: string }
  | { phase: "waiting"; message: string };

export function useClaimSender(onSent: (claim: Claim, item: Pending) => void, store: Store = deviceStore()) {
  const [state, setState] = useState<SenderState>({ phase: "idle" });
  const [queued, setQueued] = useState<Pending[]>([]);
  const [error, setError] = useState<string | null>(null);
  const busy = useRef(false);
  const timer = useRef<number | undefined>(undefined);
  const onSentRef = useRef(onSent);
  onSentRef.current = onSent;
  const storeRef = useRef(store);

  const refresh = useCallback(async () => setQueued(await storeRef.current.all()), []);

  const attempt = useCallback(
    async (item: Pending): Promise<boolean> => {
      if (busy.current) return false;
      busy.current = true;
      setError(null);
      setState({ phase: "sending", progress: 0, key: item.key });
      try {
        const { toFormData } = await import("./outbox");
        const claim = await postWithProgress<Claim>("/claims", toFormData(item), {
          key: item.key,
          onProgress: (progress) => setState({ phase: "sending", progress, key: item.key }),
        });
        await storeRef.current.remove(item.key);
        setState({ phase: "idle" });
        await refresh();
        onSentRef.current(claim, item);
        return true;
      } catch (e) {
        if (!isRetryable(e)) {
          await storeRef.current.remove(item.key); // the server said no: retrying cannot help
          setState({ phase: "idle" });
          setError((e as Error).message);
          await refresh();
          return false;
        }
        const next = { ...item, attempts: item.attempts + 1 };
        const why = cannotQueue(await storeRef.current.all(), next);
        if (why) {
          setState({ phase: "idle" });
          setError(why);
        } else {
          await storeRef.current.put(next);
          setState({ phase: "waiting", message: "No connection. Your upload is saved on this phone and will be sent again." });
          window.clearTimeout(timer.current);
          timer.current = window.setTimeout(() => void flush(), backoffMs(next.attempts));
        }
        await refresh();
        return false;
      } finally {
        busy.current = false;
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [refresh],
  );

  /** Try the oldest waiting upload now; the next one follows when it succeeds. */
  const flush = useCallback(async () => {
    const [first] = await storeRef.current.all();
    if (first && (await attempt(first))) void flush();
  }, [attempt]);

  useEffect(() => {
    void refresh();
    const online = () => void flush();
    window.addEventListener("online", online);
    return () => {
      window.removeEventListener("online", online);
      window.clearTimeout(timer.current);
    };
  }, [refresh, flush]);

  return {
    state,
    queued,
    error,
    send: attempt,
    retryNow: flush,
    discard: async (key: string) => {
      await storeRef.current.remove(key);
      await refresh();
    },
    clearAll: async () => {
      await storeRef.current.clear();
      window.clearTimeout(timer.current);
      setState({ phase: "idle" });
      await refresh();
    },
  };
}
