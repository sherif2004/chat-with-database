import { useState } from "react";
import { THEMES, getTheme, setTheme } from "../theme";
import Icon from "./Icon";

const ICONS = { system: "monitor", light: "sun", dark: "moon" };
const LABELS = { system: "System", light: "Light", dark: "Dark" };

export default function ThemeToggle({ className = "" }) {
  const [theme, setCurrent] = useState(getTheme);
  const next = THEMES[(THEMES.indexOf(theme) + 1) % THEMES.length];

  function cycle() {
    setTheme(next);
    setCurrent(next);
  }

  return (
    <button
      type="button"
      className={`icon-button theme-toggle ${className}`}
      onClick={cycle}
      aria-label={`Theme: ${LABELS[theme]}. Switch to ${LABELS[next]}.`}
      title={`Theme: ${LABELS[theme]}`}
    >
      <Icon name={ICONS[theme]} size={18} />
    </button>
  );
}
