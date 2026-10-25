import { create } from "zustand";

export type ThemePreference = "system" | "light" | "dark";
export type DetailPreference = "adaptive" | "standard" | "preview";

type Preferences = {
  theme: ThemePreference;
  detail: DetailPreference;
  showPerformance: boolean;
  setTheme: (theme: ThemePreference) => void;
  setDetail: (detail: DetailPreference) => void;
  setShowPerformance: (value: boolean) => void;
};

const STORAGE_KEY = "medtwin.preferences.v1";

function read(): Partial<Preferences> {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Partial<Preferences>) : {};
  } catch {
    return {};
  }
}

function write(state: Pick<Preferences, "theme" | "detail" | "showPerformance">): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // Storage may be unavailable (private mode); preferences then last for the session.
  }
}

const initial = read();

export const usePreferences = create<Preferences>((set, get) => ({
  theme: initial.theme ?? "system",
  detail: initial.detail ?? "adaptive",
  showPerformance: initial.showPerformance ?? false,
  setTheme: (theme) => {
    set({ theme });
    write({ theme, detail: get().detail, showPerformance: get().showPerformance });
    applyTheme(theme);
  },
  setDetail: (detail) => {
    set({ detail });
    write({ theme: get().theme, detail, showPerformance: get().showPerformance });
  },
  setShowPerformance: (showPerformance) => {
    set({ showPerformance });
    write({ theme: get().theme, detail: get().detail, showPerformance });
  },
}));

const media = typeof window !== "undefined" ? window.matchMedia("(prefers-color-scheme: dark)") : null;

export function applyTheme(theme: ThemePreference): void {
  const dark = theme === "dark" || (theme === "system" && Boolean(media?.matches));
  document.documentElement.classList.toggle("dark", dark);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
}

media?.addEventListener("change", () => applyTheme(usePreferences.getState().theme));
applyTheme(usePreferences.getState().theme);
