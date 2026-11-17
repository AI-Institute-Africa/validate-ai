import { describe, expect, it } from "vitest";
import { UNDO_SECONDS, cancel, tick, type Delayed } from "./undo";

const item = (id: number, left = 3): Delayed => ({ id, label: `a${id}`, left, run: () => {} });

describe("tick", () => {
  it("counts down and releases an item only when it reaches zero", () => {
    let list = [item(1, 2), item(2, 3)];
    let r = tick(list);
    expect(r.due).toEqual([]);
    expect(r.keep.map((d) => d.left)).toEqual([1, 2]);
    r = tick(r.keep);
    expect(r.due.map((d) => d.id)).toEqual([1]);
    expect(r.keep.map((d) => d.id)).toEqual([2]);
  });
  it("does not mutate its input", () => {
    const list = [item(1, 2)];
    tick(list);
    expect(list[0].left).toBe(2);
  });
});

describe("cancel", () => {
  it("removes only that action, so it is never sent", () => {
    const list = [item(1), item(2)];
    expect(cancel(list, 1).map((d) => d.id)).toEqual([2]);
    expect(cancel(list, 99)).toHaveLength(2);
  });
});

it("gives the reviewer a few seconds, not an instant", () => {
  expect(UNDO_SECONDS).toBeGreaterThanOrEqual(5);
});
