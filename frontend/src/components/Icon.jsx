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
  palette: "M12 3a9 9 0 100 18c1.1 0 2-.9 2-2 0-.5-.2-1-.5-1.3-.3-.4-.5-.8-.5-1.3 0-1.1.9-2 2-2h2.4A3.6 3.6 0 0021 10.8C21 6.5 17 3 12 3zM7.5 11h.01M10 7.5h.01M14.5 7.5h.01",
  sun: "M12 8a4 4 0 100 8 4 4 0 000-8zM12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4",
  moon: "M20 14.5A8 8 0 019.5 4a8 8 0 1010.5 10.5z",
  monitor: "M3 5h18v11H3zM8 20h8M12 16v4",
  up: "M12 19V5M6 11l6-6 6 6",
  down: "M12 5v14M6 13l6 6 6-6",
  users: "M16 20v-1.5a3.5 3.5 0 00-3.5-3.5h-5A3.5 3.5 0 004 18.5V20M10 12a3.5 3.5 0 100-7 3.5 3.5 0 000 7zM20 20v-1.5a3.5 3.5 0 00-2.6-3.4M15.5 5.2a3.5 3.5 0 010 6.6",
  activity: "M3 12h4l3-8 4 16 3-8h4",
  logout: "M10 4H5v16h5M15 8l4 4-4 4M19 12H9",
  back: "M19 12H5M11 6l-6 6 6 6",
  search: "M11 4a7 7 0 100 14 7 7 0 000-14zM20 20l-4-4",
  eye: "M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12zM12 9a3 3 0 100 6 3 3 0 000-6z",
  alert: "M12 4l9 16H3L12 4zM12 10v4M12 17.5h.01",
  refresh2: "M4 12a8 8 0 0114-5.3M18 3v4h-4M20 12a8 8 0 01-14 5.3M6 21v-4h4",
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
