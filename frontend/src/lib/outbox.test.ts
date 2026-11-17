import { describe, expect, it } from "vitest";
import { ApiError, NetworkError } from "../api";
import { MAX_BYTES, MAX_ITEMS, backoffMs, cannotQueue, isRetryable, memoryStore, newKey, type Pending } from "./outbox";

const item = (key: string, bytes = 10): Pending => ({
  key,
  createdAt: Date.now(),
  attempts: 0,
  fields: {},
  files: [{ name: "a.jpg", type: "image/jpeg", blob: new Blob([new Uint8Array(bytes)]) }],
  label: "AB-123",
});

describe("isRetryable", () => {
  it("retries network trouble and busy servers only", () => {
    expect(isRetryable(new NetworkError("x"))).toBe(true);
    for (const s of [408, 429, 502, 503, 504]) expect(isRetryable(new ApiError(s, "x"))).toBe(true);
    for (const s of [400, 401, 403, 409, 413, 422]) expect(isRetryable(new ApiError(s, "x"))).toBe(false);
    expect(isRetryable(new DOMException("Aborted", "AbortError"))).toBe(false);
    expect(isRetryable(new Error("boom"))).toBe(false);
  });
});

describe("backoffMs", () => {
  it("doubles and is capped", () => {
    expect([0, 1, 2, 3].map(backoffMs)).toEqual([2000, 4000, 8000, 16000]);
    expect(backoffMs(20)).toBe(60_000);
    expect(backoffMs(-3)).toBe(2000);
  });
});

describe("cannotQueue", () => {
  it("limits how many and how much can wait", () => {
    const full = Array.from({ length: MAX_ITEMS }, (_, i) => item(`k${i}`));
    expect(cannotQueue(full, item("new"))).toMatch(/Up to/);
    expect(cannotQueue([item("a", MAX_BYTES)], item("b", 1))).toMatch(/Too much/);
    expect(cannotQueue([], item("a"))).toBeNull();
  });
  it("lets an already saved upload be updated even when the queue is full", () => {
    const full = Array.from({ length: MAX_ITEMS }, (_, i) => item(`k${i}`));
    expect(cannotQueue(full, item("k2"))).toBeNull();
  });
});

describe("memoryStore", () => {
  it("keeps order, replaces by key, removes and clears", async () => {
    const s = memoryStore();
    await s.put({ ...item("b"), createdAt: 2 });
    await s.put({ ...item("a"), createdAt: 1 });
    expect((await s.all()).map((p) => p.key)).toEqual(["a", "b"]);
    await s.put({ ...item("a"), createdAt: 1, attempts: 3 });
    expect((await s.all())[0].attempts).toBe(3);
    await s.remove("a");
    expect((await s.all()).length).toBe(1);
    await s.clear();
    expect(await s.all()).toEqual([]);
  });
});

describe("newKey", () => {
  it("makes a key the server accepts, different each time", () => {
    const a = newKey();
    expect(a).toMatch(/^[A-Za-z0-9._:-]{8,80}$/);
    expect(newKey()).not.toBe(a);
  });
});
