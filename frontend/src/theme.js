const KEY = "theme";

export const THEMES = ["system", "light", "dark"];

export function getTheme() {
  try {
    const saved = localStorage.getItem(KEY);
    return saved === "light" || saved === "dark" ? saved : "system";
  } catch {
    return "system";
  }
}

/** Applies a theme now and remembers it. "system" follows the OS. */
export function setTheme(theme) {
  const root = document.documentElement;

  if (theme === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", theme);

  try {
    if (theme === "system") localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, theme);
  } catch {
    // Storage blocked: the choice still applies until the page closes.
  }
}
