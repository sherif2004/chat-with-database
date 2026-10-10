import { useEffect, useRef, useState } from "react";
import {
  ACCENTS,
  PAGES,
  THEMES,
  getAccent,
  getPage,
  getTheme,
  setAccent,
  setPage,
  setTheme,
} from "../theme";
import Icon from "./Icon";

const THEME_ICONS = { system: "monitor", light: "sun", dark: "moon" };
const THEME_LABELS = { system: "System", light: "Light", dark: "Dark" };

/** A popover for the theme (system, light, dark) and the main color. Changes apply live. */
export default function AppearanceMenu({ placement = "up" }) {
  const [open, setOpen] = useState(false);
  const [theme, setThemeState] = useState(getTheme);
  const [accent, setAccentState] = useState(getAccent);
  const [page, setPageState] = useState(getPage);
  const rootRef = useRef(null);
  const buttonRef = useRef(null);

  useEffect(() => {
    if (!open) return;

    function onPointerDown(event) {
      if (!rootRef.current?.contains(event.target)) setOpen(false);
    }
    function onKeyDown(event) {
      if (event.key === "Escape") {
        event.stopPropagation();
        setOpen(false);
        buttonRef.current?.focus();
      }
    }

    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div className="appearance" ref={rootRef}>
      <button
        ref={buttonRef}
        type="button"
        className="icon-button"
        aria-label="Appearance"
        aria-expanded={open}
        aria-haspopup="true"
        title="Appearance"
        onClick={() => setOpen((value) => !value)}
      >
        <Icon name="palette" size={18} />
      </button>

      {open && (
        <div className={`appearance-panel appearance-${placement}`}>
          <fieldset className="appearance-group">
            <legend className="appearance-heading">Theme</legend>
            <div className="segmented">
              {THEMES.map((value) => (
                <label key={value} className="segment">
                  <input
                    type="radio"
                    name="theme"
                    value={value}
                    checked={theme === value}
                    onChange={() => {
                      setTheme(value);
                      setThemeState(value);
                    }}
                  />
                  <span>
                    <Icon name={THEME_ICONS[value]} size={14} />
                    {THEME_LABELS[value]}
                  </span>
                </label>
              ))}
            </div>
          </fieldset>

          <fieldset className="appearance-group">
            <legend className="appearance-heading">
              Page color
              <span className="appearance-value">{PAGES.find((p) => p.id === page)?.label}</span>
            </legend>
            <div className="swatches">
              {PAGES.map((option) => (
                <label key={option.id} className="swatch" title={option.label}>
                  <input
                    type="radio"
                    name="page"
                    value={option.id}
                    checked={page === option.id}
                    onChange={() => {
                      setPage(option.id);
                      setPageState(option.id);
                    }}
                  />
                  <span
                    className="swatch-dot swatch-page"
                    style={{
                      background: `light-dark(${option.light.bg}, ${option.dark.bg})`,
                      borderColor: `light-dark(${option.light.border}, ${option.dark.border})`,
                    }}
                  >
                    <span
                      className="swatch-chip"
                      style={{
                        background: `light-dark(${option.light.surface}, ${option.dark.surface})`,
                        borderColor: `light-dark(${option.light.border}, ${option.dark.border})`,
                      }}
                    >
                      {page === option.id && <Icon name="check" size={12} />}
                    </span>
                  </span>
                  <span className="sr-only">{option.label}</span>
                </label>
              ))}
            </div>
          </fieldset>

          <fieldset className="appearance-group">
            <legend className="appearance-heading">
              Main color
              <span className="appearance-value">{ACCENTS.find((a) => a.id === accent)?.label}</span>
            </legend>
            <div className="swatches">
              {ACCENTS.map((option) => (
                <label key={option.id} className="swatch" title={option.label}>
                  <input
                    type="radio"
                    name="accent"
                    value={option.id}
                    checked={accent === option.id}
                    onChange={() => {
                      setAccent(option.id);
                      setAccentState(option.id);
                    }}
                  />
                  <span
                    className="swatch-dot"
                    style={{
                      background: `light-dark(${option.light.fill}, ${option.dark.fill})`,
                      color: `light-dark(${option.light.on}, ${option.dark.on})`,
                    }}
                  >
                    {accent === option.id && <Icon name="check" size={14} />}
                  </span>
                  <span className="sr-only">{option.label}</span>
                </label>
              ))}
            </div>
          </fieldset>
        </div>
      )}
    </div>
  );
}
