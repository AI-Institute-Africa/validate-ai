// A small set of line icons, one stroke weight, drawn in the current text colour. They replace emoji,
// which render differently on every phone and make an interface look generic.

const PATHS: Record<string, string> = {
  home: "M4 11.5 12 5l8 6.5M6.5 10v8.5h11V10",
  receipt: "M6 3.5h12v17l-2.2-1.5-1.9 1.5-1.9-1.5-1.9 1.5-2.1-1.5V3.5ZM9 8.5h6M9 12h6M9 15.5h3",
  text: "M4 7V5.5h16V7M12 5.5v13M9 18.5h6",
  inbox: "M4 13.5 6.5 5h11L20 13.5M4 13.5V19h16v-5.5M4 13.5h4.5a3.5 3.5 0 0 0 7 0H20",
  shield: "M12 3.5 5 6v5.5c0 4.2 2.9 7.3 7 9 4.1-1.7 7-4.8 7-9V6l-7-2.5ZM9.2 12l2 2 3.6-4",
  bank: "M3.5 9.5 12 4l8.5 5.5M5.5 10v7.5M9.5 10v7.5M14.5 10v7.5M18.5 10v7.5M3.5 20h17",
  file: "M7 3.5h6.5L18 8v12.5H7V3.5ZM13.5 3.5V8H18M9.5 12.5h6M9.5 16h6",
  bolt: "M13 3.5 6 13h5l-1 7.5L18 11h-5.2L13 3.5Z",
  id: "M3.5 6.5h17v11h-17v-11ZM8.5 11a1.7 1.7 0 1 0 0-.01M6.2 15c.5-1.6 1.4-2.2 2.3-2.2s1.8.6 2.3 2.2M13.5 10h4.5M13.5 13h4.5",
  search: "M10.5 17a6.5 6.5 0 1 1 0-13 6.5 6.5 0 0 1 0 13ZM15.5 15.5 20 20",
  bell: "M6.5 16.5v-5a5.5 5.5 0 0 1 11 0v5l1.5 1.5h-14l1.5-1.5ZM10.2 20.5h3.6",
  chart: "M4.5 19.5V5M4.5 19.5h15M8.5 16v-4M12.5 16V8.5M16.5 16v-6.5",
  sliders: "M5 7h9M18 7h1M5 17h1M10 17h9M14 4.5v5M8 14.5v5",
  flask: "M9.5 3.5h5M10.5 3.5v6L5.5 18a1.8 1.8 0 0 0 1.6 2.5h9.8a1.8 1.8 0 0 0 1.6-2.5l-5-8.5v-6M8 15h8",
  camera: "M4 8.5h3l1.5-2.5h7L17 8.5h3v10H4v-10ZM12 16.5a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z",
  upload: "M12 15.5V5M7.5 9.5 12 5l4.5 4.5M5 15.5v3h14v-3",
  check: "M5 12.5 10 17.5 19 7",
  arrow: "M5 12h14M13.5 6.5 19 12l-5.5 5.5",
  play: "M8 5.5v13l10.5-6.5L8 5.5Z",
  refresh: "M19 8.5A7.5 7.5 0 0 0 5.8 7.2L4.5 9M4.5 5v4h4M5 15.5a7.5 7.5 0 0 0 13.2 1.3l1.3-1.8M19.5 19v-4h-4",
  close: "M6.5 6.5l11 11M17.5 6.5l-11 11",
  scan: "M4 8V5.5A1.5 1.5 0 0 1 5.5 4H8M16 4h2.5A1.5 1.5 0 0 1 20 5.5V8M20 16v2.5a1.5 1.5 0 0 1-1.5 1.5H16M8 20H5.5A1.5 1.5 0 0 1 4 18.5V16M4 12h16",
  download: "M12 4.5v11M7.5 11.5 12 16l4.5-4.5M5 19.5h14",
  menu: "M4.5 7h15M4.5 12h15M4.5 17h15",
  lock: "M6.5 11h11v8.5h-11V11ZM8.5 11V8.5a3.5 3.5 0 0 1 7 0V11",
  crop: "M7 3.5v13.5h13.5M3.5 7H17v13.5",
  rotate: "M19 8.5A7.5 7.5 0 0 0 5.8 7.2L4.5 9M4.5 5v4h4",
  sun: "M12 16.5a4.5 4.5 0 1 0 0-9 4.5 4.5 0 0 0 0 9ZM12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6 7 7M17 17l1.4 1.4M5.6 18.4 7 17M17 7l1.4-1.4",
  moon: "M19.5 14.5A7.5 7.5 0 0 1 9.5 4.5a7.5 7.5 0 1 0 10 10Z",
  monitor: "M4 5.5h16v11H4v-11ZM9 20h6M12 16.5V20",
  keyboard: "M3.5 7h17v10h-17V7ZM7 10.5h.01M10.5 10.5h.01M14 10.5h.01M17 10.5h.01M8 14h8",
};

export type IconName = keyof typeof PATHS;

export function Icon({ name, size = 18, className }: { name: IconName | string; size?: number; className?: string }) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      focusable="false"
    >
      <path d={PATHS[name] ?? PATHS.file} />
    </svg>
  );
}
