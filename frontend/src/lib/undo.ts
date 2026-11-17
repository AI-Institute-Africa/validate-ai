// "Undo" for actions that cannot be taken back once sent (a reject tells the payer and closes the
// claim). The action is only sent when the countdown ends, so Undo is a real cancel.

export type Delayed = { id: number; label: string; left: number; run: () => void | Promise<void> };

export const UNDO_SECONDS = 8;

/** One second passes: everything counts down and what reaches zero is due. */
export function tick(list: Delayed[]): { keep: Delayed[]; due: Delayed[] } {
  const next = list.map((d) => ({ ...d, left: d.left - 1 }));
  return { keep: next.filter((d) => d.left > 0), due: next.filter((d) => d.left <= 0) };
}

export function cancel(list: Delayed[], id: number): Delayed[] {
  return list.filter((d) => d.id !== id);
}
