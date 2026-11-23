import { useEffect, useState } from "react";

export type Theme = "light" | "dark";
const KEY = "dk-sales-theme";

/** Saved choice first, then the system setting. index.html applies the same rule before React loads. */
function initialTheme(): Theme {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === "light" || saved === "dark") return saved;
  } catch {
    // storage blocked (private mode): fall through to the system setting
  }
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(initialTheme);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  const toggle = () =>
    setTheme((current) => {
      const next = current === "dark" ? "light" : "dark";
      try {
        localStorage.setItem(KEY, next); // only an explicit choice is remembered
      } catch {
        // not saved; the switch still works for this visit
      }
      return next;
    });

  return [theme, toggle];
}
