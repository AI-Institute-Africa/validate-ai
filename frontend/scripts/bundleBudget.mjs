// Guard the route-level split: the payer shell must stay small, and no page may grow into a
// second monolith. Run after `npm run build` (`npm run budget`). CI runs this as a build gate.

import { readFileSync, readdirSync } from "node:fs";
import { basename, join } from "node:path";
import { gzipSync } from "node:zlib";

const DIST = "dist";
const ASSETS = join(DIST, "assets");
const KB = 1024;

// Headroom over the current build (initial 94 kB gz, largest route 10 kB gz).
const LIMITS = {
  initialJs: 110,
  initialCss: 18,
  routeJs: 14,
  routeCss: 5,
};

const fail = (msg) => {
  console.error(`bundle budget: ${msg}`);
  process.exit(1);
};

let html;
try {
  html = readFileSync(join(DIST, "index.html"), "utf8");
} catch {
  fail("dist/index.html is missing — run `npm run build` first");
}

const initial = new Set(
  [...html.matchAll(/(?:src|href)="\/?(assets\/[^"?]+\.(?:js|css))"/g)].map((m) => basename(m[1])),
);
if (![...initial].some((f) => f.endsWith(".js"))) fail("could not find the entry script in dist/index.html");

const size = (file) => {
  const raw = readFileSync(join(ASSETS, file));
  return { raw: raw.length, gz: gzipSync(raw, { level: 9 }).length };
};

const groups = { initialJs: [], initialCss: [], routeJs: [], routeCss: [] };
for (const file of readdirSync(ASSETS)) {
  if (!/\.(js|css)$/.test(file)) continue;
  const kind = initial.has(file)
    ? file.endsWith(".js") ? "initialJs" : "initialCss"
    : file.endsWith(".js") ? "routeJs" : "routeCss";
  groups[kind].push({ file, ...size(file) });
}

const total = (items, key) => items.reduce((n, item) => n + item[key], 0);
const largest = (items) => items.reduce((max, item) => Math.max(max, item.gz), 0) / KB;

const rows = [
  ["initial JS", groups.initialJs, "initialJs", total(groups.initialJs, "gz") / KB],
  ["initial CSS", groups.initialCss, "initialCss", total(groups.initialCss, "gz") / KB],
  ["largest route JS", groups.routeJs, "routeJs", largest(groups.routeJs)],
  ["largest route CSS", groups.routeCss, "routeCss", largest(groups.routeCss)],
];

let over = false;
console.log("bundle budget (gzip):");
for (const [label, items, limitKey, used] of rows) {
  const limit = LIMITS[limitKey];
  const ok = used <= limit;
  over ||= !ok;
  console.log(`  ${ok ? "ok  " : "FAIL"} ${label.padEnd(18)} ${used.toFixed(1).padStart(6)} / ${limit} kB  (${items.length} files)`);
}
if (over) fail("a budget was exceeded; split the page or trim the bundle");
console.log(`bundle budget: ok (${groups.routeJs.length} route chunks remain lazy-loaded)`);
