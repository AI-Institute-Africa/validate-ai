/** Pointer and scroll flair, installed once: a spotlight that follows the cursor on cards, a slight 3D tilt on
 *  tiles, and a reveal as sections scroll into view. Pure decoration: everything is skipped when the device asks
 *  for less motion, and the page reads the same without it. */

const SPOT = ".card, .scn-card, .recent, .stat, .tour-step, .capture, a.btn, button.btn";
const TILT = ".scn-card, .recent";
const REVEAL = ".section-title, .how > .card, .stats, .table-wrap";

export function installFlair(): void {
  if (typeof document === "undefined" || typeof matchMedia !== "function") return;
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const fine = matchMedia("(hover: hover) and (pointer: fine)").matches;

  if (fine) {
    let raf = 0;
    document.addEventListener(
      "pointermove",
      (e) => {
        const t = e.target as Element | null;
        const el = t?.closest?.(SPOT) as HTMLElement | null;
        if (!el) return;
        cancelAnimationFrame(raf);
        raf = requestAnimationFrame(() => {
          const r = el.getBoundingClientRect();
          const x = e.clientX - r.left;
          const y = e.clientY - r.top;
          el.style.setProperty("--mx", `${x}px`);
          el.style.setProperty("--my", `${y}px`);
          if (el.matches(TILT)) {
            el.style.setProperty("--ry", `${((x / r.width) - 0.5) * 7}deg`);
            el.style.setProperty("--rx", `${(0.5 - y / r.height) * 7}deg`);
          }
        });
      },
      { passive: true },
    );
    document.addEventListener(
      "pointerout",
      (e) => {
        const el = (e.target as Element | null)?.closest?.(TILT) as HTMLElement | null;
        if (el && !el.contains(e.relatedTarget as Node | null)) {
          el.style.removeProperty("--rx");
          el.style.removeProperty("--ry");
        }
      },
      { passive: true },
    );
  }

  if (typeof IntersectionObserver === "function" && typeof MutationObserver === "function") {
    const io = new IntersectionObserver(
      (entries) => {
        for (const en of entries) {
          if (en.isIntersecting) {
            en.target.classList.add("rs-in");
            io.unobserve(en.target);
          }
        }
      },
      { rootMargin: "0px 0px -8% 0px" },
    );
    const arm = (root: ParentNode) => {
      root.querySelectorAll?.(REVEAL).forEach((el) => {
        if (el.classList.contains("rs")) return;
        // only things that start below the fold wait; what is already visible stays put
        const top = el.getBoundingClientRect().top;
        if (top < window.innerHeight * 0.92) return;
        el.classList.add("rs");
        io.observe(el);
      });
    };
    arm(document);
    new MutationObserver((muts) => {
      for (const m of muts) m.addedNodes.forEach((n) => n.nodeType === 1 && arm(n as Element));
    }).observe(document.body, { childList: true, subtree: true });
  }
}
