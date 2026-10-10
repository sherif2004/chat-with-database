const THEME_KEY = "theme";
const ACCENT_KEY = "accent";
const PAGE_KEY = "page";
const THEME_CSS_KEY = "theme-css";

export const THEMES = ["system", "light", "dark"];

/**
 * Selectable main colors. Each defines the brand hue (rings, borders, tints),
 * the accent used for text and links, the fill behind white (or `on`) text,
 * for both modes. Contrast is checked per mode: `on` on `fill` and `accent`
 * on the surfaces are at least 4.5:1, `brand` on surfaces at least 3:1.
 * "blue" is the stylesheet default and sets nothing.
 */
export const ACCENTS = [
  {
    id: "blue",
    label: "Blue",
    light: { brand: "#0a84ff", accent: "#0066d6", fill: "#0066d6", on: "#ffffff" },
    dark: { brand: "#3b9cff", accent: "#3b9cff", fill: "#0a6fe0", on: "#ffffff" },
  },
  {
    id: "indigo",
    label: "Indigo",
    light: { brand: "#6366f1", accent: "#4f46e5", fill: "#4f46e5", on: "#ffffff" },
    dark: { brand: "#8b8ff5", accent: "#a5acff", fill: "#5457e0", on: "#ffffff" },
  },
  {
    id: "violet",
    label: "Violet",
    light: { brand: "#8b5cf6", accent: "#7c3aed", fill: "#7c3aed", on: "#ffffff" },
    dark: { brand: "#b08af7", accent: "#c4a5fa", fill: "#7040d8", on: "#ffffff" },
  },
  {
    id: "rose",
    label: "Rose",
    light: { brand: "#f43f5e", accent: "#be123c", fill: "#e11d48", on: "#ffffff" },
    dark: { brand: "#fb7185", accent: "#fda4af", fill: "#d6264a", on: "#ffffff" },
  },
  {
    id: "amber",
    label: "Amber",
    light: { brand: "#c2650a", accent: "#a8480a", fill: "#c2410c", on: "#ffffff" },
    dark: { brand: "#fbbf24", accent: "#fdba74", fill: "#c2410c", on: "#ffffff" },
  },
  {
    id: "graphite",
    label: "Graphite",
    light: { brand: "#52525b", accent: "#27272a", fill: "#27272a", on: "#ffffff" },
    dark: { brand: "#a1a1aa", accent: "#e4e4e7", fill: "#e4e4e7", on: "#16171a" },
  },
];

/**
 * Selectable page colors: the background, panel surfaces, borders and the
 * assistant bubble, for both modes. Text and accent colors are untouched.
 * Each palette is checked against both text colors and all accents: text at
 * least 7:1, muted text and accent text at least 4.5:1, field borders at
 * least 3:1. "neutral" is the stylesheet default and sets nothing.
 */
export const PAGES = [
  {
    id: "neutral",
    label: "Neutral",
    light: { bg: "#f5f5f7", surface: "#ffffff", alt: "#f7f8fa", border: "#e3e4e8", bubble: "#f0f1f4" },
    dark: { bg: "#16171a", surface: "#1e1f23", alt: "#232428", border: "#302f34", bubble: "#2a2b30" },
  },
  {
    id: "paper",
    label: "Paper",
    light: { bg: "#f6f2ea", surface: "#fffdf8", alt: "#faf6ee", border: "#e6dfd0", bubble: "#f1ebdf" },
    dark: { bg: "#1a1814", surface: "#211e19", alt: "#26231d", border: "#3a352c", bubble: "#2f2b24" },
  },
  {
    id: "slate",
    label: "Slate",
    light: { bg: "#eef2f7", surface: "#fbfcfe", alt: "#f3f6fa", border: "#d9e1ec", bubble: "#e8eef6" },
    dark: { bg: "#12171f", surface: "#181e28", alt: "#1d2430", border: "#2c3647", bubble: "#243044" },
  },
  {
    id: "sage",
    label: "Sage",
    light: { bg: "#eff3ee", surface: "#fbfdfb", alt: "#f4f7f3", border: "#dbe3d8", bubble: "#e8efe5" },
    dark: { bg: "#121714", surface: "#181e1a", alt: "#1d241f", border: "#2c372f", bubble: "#25302a" },
  },
  {
    id: "blush",
    label: "Blush",
    light: { bg: "#f8f0f1", surface: "#fffcfc", alt: "#fbf5f6", border: "#ecdcdf", bubble: "#f4e8ea" },
    dark: { bg: "#1a1415", surface: "#211a1c", alt: "#271f21", border: "#3b2d30", bubble: "#30262a" },
  },
  {
    id: "mist",
    label: "Mist",
    light: { bg: "#f1f0f8", surface: "#fcfcff", alt: "#f6f5fb", border: "#dedcee", bubble: "#ebe9f5" },
    dark: { bg: "#14131c", surface: "#1a1925", alt: "#201f2d", border: "#302e44", bubble: "#282639" },
  },
];

function read(key) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key, value) {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    // Storage blocked: the choice still applies until the page closes.
  }
}

export function getTheme() {
  const saved = read(THEME_KEY);
  return saved === "light" || saved === "dark" ? saved : "system";
}

/** Applies a theme now and remembers it. "system" follows the OS. */
export function setTheme(theme) {
  const root = document.documentElement;

  if (theme === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", theme);

  write(THEME_KEY, theme === "system" ? null : theme);
}

export function getAccent() {
  const saved = read(ACCENT_KEY);
  return ACCENTS.some((accent) => accent.id === saved) ? saved : "blue";
}

const ACCENT_PROPERTIES = ["--brand", "--accent", "--accent-fill", "--accent-text"];
const PAGE_PROPERTIES = ["--bg", "--surface", "--surface-alt", "--border", "--bubble-assistant"];

function pair(option, key) {
  return `light-dark(${option.light[key]}, ${option.dark[key]})`;
}

/** Remembers the combined inline style so index.html can replay it before first paint. */
function persistStyle() {
  const css = document.documentElement.style.cssText;
  write(THEME_CSS_KEY, css || null);
}

/** Applies a main color to both modes at once and remembers it. */
export function setAccent(id) {
  const accent = ACCENTS.find((candidate) => candidate.id === id) || ACCENTS[0];
  const style = document.documentElement.style;

  if (accent.id === "blue") {
    ACCENT_PROPERTIES.forEach((name) => style.removeProperty(name));
    write(ACCENT_KEY, null);
  } else {
    style.setProperty("--brand", pair(accent, "brand"));
    style.setProperty("--accent", pair(accent, "accent"));
    style.setProperty("--accent-fill", pair(accent, "fill"));
    style.setProperty("--accent-text", pair(accent, "on"));
    write(ACCENT_KEY, accent.id);
  }

  persistStyle();
}

export function getPage() {
  const saved = read(PAGE_KEY);
  return PAGES.some((page) => page.id === saved) ? saved : "neutral";
}

/** Applies a page color palette to both modes at once and remembers it. */
export function setPage(id) {
  const page = PAGES.find((candidate) => candidate.id === id) || PAGES[0];
  const style = document.documentElement.style;

  if (page.id === "neutral") {
    PAGE_PROPERTIES.forEach((name) => style.removeProperty(name));
    write(PAGE_KEY, null);
  } else {
    style.setProperty("--bg", pair(page, "bg"));
    style.setProperty("--surface", pair(page, "surface"));
    style.setProperty("--surface-alt", pair(page, "alt"));
    style.setProperty("--border", pair(page, "border"));
    style.setProperty("--bubble-assistant", pair(page, "bubble"));
    write(PAGE_KEY, page.id);
  }

  persistStyle();
}
