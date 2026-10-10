const PATHS = {
  menu: "M4 7h16M4 12h16M4 17h16",
  plus: "M12 5v14M5 12h14",
  close: "M6 6l12 12M18 6L6 18",
  stop: "M7 7h10v10H7z",
  send: "M12 19V5M6 11l6-6 6 6",
  database: "M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zM4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6",
  trash: "M5 7h14M10 7V4h4v3M7 7l1 13h8l1-13",
  pencil: "M4 20l4-1 11-11-3-3L5 16l-1 4zM14 6l3 3",
  copy: "M8 8h11v12H8zM5 16V4h11",
  refresh: "M20 11a8 8 0 10-2.3 5.7M20 5v6h-6",
  download: "M12 4v11M7 11l5 5 5-5M5 20h14",
  chart: "M5 20V10M12 20V4M19 20v-7",
  table: "M4 5h16v14H4zM4 10h16M10 5v14",
  check: "M5 12l5 5 9-10",
  up: "M12 19V5M6 11l6-6 6 6",
  down: "M12 5v14M6 13l6 6 6-6",
};

export default function Icon({ name, size = 16 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
