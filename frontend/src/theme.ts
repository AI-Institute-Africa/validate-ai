// Theme: "light" | "dark" | "auto" (follows the OS). Stored in localStorage.
import { useEffect, useState } from "react";

export type ThemeChoice = "light" | "dark" | "auto";

const KEY = "validate-theme";

function stored(): ThemeChoice {
  const v = localStorage.getItem(KEY);
  return v === "light" || v === "dark" ? v : "auto";
}

function apply(choice: ThemeChoice) {
  // "auto" must not pin an attribute: tokens.css follows the OS media query in that case,
  // so an OS switch from light to dark is picked up immediately, even with no menu open.
  if (choice === "auto") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = choice;
}

// The theme lives in the persona menu, which is only mounted while that menu is open. Apply the
// saved choice when this module loads so a stored dark theme is not lost until a user opens it.
apply(stored());

export function useTheme() {
  const [choice, setChoice] = useState<ThemeChoice>(() => stored());

  useEffect(() => {
    apply(choice);
  }, [choice]);

  const cycle = () => {
    const next: ThemeChoice = choice === "auto" ? "light" : choice === "light" ? "dark" : "auto";
    localStorage.setItem(KEY, next);
    setChoice(next);
  };

  const icon = choice === "auto" ? "🖥" : choice === "dark" ? "🌙" : "☀";
  const label = choice === "auto" ? "Theme: auto" : choice === "dark" ? "Theme: dark" : "Theme: light";
  return { choice, cycle, icon, label };
}
