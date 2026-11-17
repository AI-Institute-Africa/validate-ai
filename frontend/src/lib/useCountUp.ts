import { useEffect, useRef, useState } from "react";

/** A number that settles to its value instead of jumping. Instant when the device asks for less motion. */
export function useCountUp(target: number | undefined, ms = 700): number | undefined {
  const [shown, setShown] = useState<number | undefined>(target);
  const from = useRef(0);
  useEffect(() => {
    if (target === undefined) return;
    const calm = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (calm || target === from.current) {
      from.current = target;
      setShown(target);
      return;
    }
    const start = performance.now();
    const base = from.current;
    let raf = 0;
    const step = (now: number) => {
      const k = Math.min(1, (now - start) / ms);
      const eased = 1 - Math.pow(1 - k, 3);
      setShown(Math.round(base + (target - base) * eased));
      if (k < 1) raf = requestAnimationFrame(step);
      else from.current = target;
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target, ms]);
  return shown;
}
