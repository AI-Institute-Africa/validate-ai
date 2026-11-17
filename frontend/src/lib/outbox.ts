// Uploads that could not be sent yet (no signal, server busy). They wait on this device, are sent
// again with the SAME Idempotency-Key (so a retry can never create a second claim), and are deleted
// as soon as they succeed. Nothing leaves the device except to the Validate server.

import { NetworkError } from "../api";

export const MAX_ITEMS = 5;
export const MAX_BYTES = 50 * 1024 * 1024;

export type StoredFile = { name: string; type: string; blob: Blob };
export type Pending = {
  key: string; // the Idempotency-Key, fixed for this upload's whole life
  createdAt: number;
  attempts: number;
  fields: Record<string, string>;
  files: StoredFile[];
  label: string; // shown to the payer, e.g. the payment code
};

/** A failure worth trying again: no connection, a timeout, a busy or restarting server. */
export function isRetryable(err: unknown): boolean {
  if (err && typeof err === "object" && "status" in err) {
    const s = (err as { status: number }).status;
    return s === 408 || s === 429 || s === 502 || s === 503 || s === 504;
  }
  return err instanceof NetworkError; // instanceof, not a class name: names are mangled in production builds
}

/** Seconds-ish backoff: 2s, 4s, 8s ... capped at 60s. Deterministic so it can be tested. */
export function backoffMs(attempt: number): number {
  return Math.min(60_000, 2_000 * 2 ** Math.max(0, attempt));
}

export const sizeOf = (p: Pending) => p.files.reduce((n, f) => n + f.blob.size, 0);

/** Why this upload cannot be saved for later, or null if it can. */
export function cannotQueue(existing: Pending[], add: Pending): string | null {
  if (existing.some((p) => p.key === add.key)) return null; // already saved: updating it
  if (existing.length >= MAX_ITEMS) return `Up to ${MAX_ITEMS} uploads can wait. Send or discard one first.`;
  const total = existing.reduce((n, p) => n + sizeOf(p), 0) + sizeOf(add);
  if (total > MAX_BYTES) return "Too much waiting to send. Send or discard one first.";
  return null;
}

export interface Store {
  all(): Promise<Pending[]>;
  put(p: Pending): Promise<void>;
  remove(key: string): Promise<void>;
  clear(): Promise<void>;
}

export function memoryStore(): Store {
  const m = new Map<string, Pending>();
  return {
    all: async () => [...m.values()].sort((a, b) => a.createdAt - b.createdAt),
    put: async (p) => void m.set(p.key, p),
    remove: async (k) => void m.delete(k),
    clear: async () => m.clear(),
  };
}

const DB = "validate-outbox";
const TABLE = "pending";

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(TABLE, { keyPath: "key" });
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

function run<T>(mode: IDBTransactionMode, fn: (s: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  return open().then(
    (db) =>
      new Promise<T>((resolve, reject) => {
        const req = fn(db.transaction(TABLE, mode).objectStore(TABLE));
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
      }),
  );
}

/** IndexedDB when the browser allows it (private windows may not); memory otherwise. */
export function deviceStore(): Store {
  if (typeof indexedDB === "undefined") return memoryStore();
  const fallback = memoryStore();
  let broken = false;
  const guard = async <T,>(real: () => Promise<T>, soft: () => Promise<T>): Promise<T> => {
    if (broken) return soft();
    try {
      return await real();
    } catch {
      broken = true;
      return soft();
    }
  };
  return {
    all: () =>
      guard(
        async () => ((await run("readonly", (s) => s.getAll())) as Pending[]).sort((a, b) => a.createdAt - b.createdAt),
        fallback.all,
      ),
    put: (p) => guard(async () => void (await run("readwrite", (s) => s.put(p))), () => fallback.put(p)),
    remove: (k) => guard(async () => void (await run("readwrite", (s) => s.delete(k))), () => fallback.remove(k)),
    clear: () => guard(async () => void (await run("readwrite", (s) => s.clear())), fallback.clear),
  };
}

export function toFormData(p: Pending): FormData {
  const fd = new FormData();
  for (const [k, v] of Object.entries(p.fields)) fd.set(k, v);
  for (const f of p.files) fd.append("file", new File([f.blob], f.name, { type: f.type }));
  return fd;
}

export function newKey(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `k-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}
