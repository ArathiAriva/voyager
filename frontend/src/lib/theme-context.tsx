"use client";

import { createContext, useContext, useEffect, useState } from "react";
import type { ThemePreference } from "@/lib/theme";

const STORAGE_KEY = "voyager-theme";

interface ThemeContextValue {
  preference: ThemePreference;
  resolved: "dark" | "light";
  setPreference: (p: ThemePreference) => void;
}

const ThemeContext = createContext<ThemeContextValue>({
  preference: "system",
  resolved: "dark",
  setPreference: () => {},
});

function getSystemMode(): "dark" | "light" {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function resolveMode(pref: ThemePreference): "dark" | "light" {
  if (pref === "dark" || pref === "light") return pref;
  return getSystemMode();
}

function applyMode(mode: "dark" | "light") {
  const root = document.documentElement;
  root.classList.remove("dark", "light");
  root.classList.add(mode);
  root.style.colorScheme = mode;
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [preference, setPreferenceState] = useState<ThemePreference>("system");
  const [resolved, setResolved] = useState<"dark" | "light">("dark");

  useEffect(() => {
    const raw = localStorage.getItem(STORAGE_KEY);
    const saved: ThemePreference =
      raw === "dark" || raw === "light" || raw === "system" ? raw : "system";
    const mode = resolveMode(saved);
    setPreferenceState(saved);
    setResolved(mode);
    applyMode(mode);
  }, []);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    function handler(e: MediaQueryListEvent) {
      if (preference === "system") {
        const mode = e.matches ? "dark" : "light";
        setResolved(mode);
        applyMode(mode);
      }
    }
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, [preference]);

  function setPreference(p: ThemePreference) {
    const mode = resolveMode(p);
    setPreferenceState(p);
    setResolved(mode);
    applyMode(mode);
    localStorage.setItem(STORAGE_KEY, p);
  }

  return (
    <ThemeContext.Provider value={{ preference, resolved, setPreference }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}
