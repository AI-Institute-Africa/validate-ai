// Official ZWG-per-USD ask rate helpers for the reviewer screens. The server is the authority
// (backend/app/fx); this only shows a conversion next to a claim.

export type Ccy = "USD" | "ZWG";
const PAIR = new Set<string>(["USD", "ZWG"]);

export const normaliseCurrency = (c: string | null | undefined): string => {
  const u = (c ?? "").toUpperCase();
  return u === "ZIG" || u === "ZWL" ? "ZWG" : u;
};

/** True when both are in the official pair and differ. */
export function isCrossCurrency(payment: string | null | undefined, invoice: string | null | undefined): boolean {
  const a = normaliseCurrency(payment);
  const b = normaliseCurrency(invoice);
  return a !== b && PAIR.has(a) && PAIR.has(b);
}

/** Convert minor units at the ask rate (ZWG per 1 USD), rounding half up like the server. */
export function convertMinor(minor: number, from: string, to: string, ask: number): number {
  const a = normaliseCurrency(from);
  const b = normaliseCurrency(to);
  if (a === b) return minor;
  if (!(ask > 0)) throw new Error("rate must be positive");
  const value = a === "USD" && b === "ZWG" ? minor * ask : minor / ask;
  return Math.floor(value + 0.5);
}

/** Gap between the converted payment and the invoice, in basis points of the invoice. */
export function gapBps(convertedMinor: number, invoiceMinor: number): number {
  return Math.round((Math.abs(convertedMinor - invoiceMinor) * 10000) / Math.max(invoiceMinor, 1));
}
