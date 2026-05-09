// Thin typed wrapper around `window.Telegram.WebApp`.
//
// We don't pull `@twa-dev/sdk` because we only use a sliver of the API
// (initData, theme params, ready, haptics). The official tag served by
// `index.html` is enough.

interface TelegramThemeParams {
  bg_color?: string;
  text_color?: string;
  hint_color?: string;
  link_color?: string;
  button_color?: string;
  button_text_color?: string;
  secondary_bg_color?: string;
  destructive_text_color?: string;
  section_header_text_color?: string;
  section_separator_color?: string;
}

interface TelegramHapticFeedback {
  impactOccurred: (style: "light" | "medium" | "heavy" | "rigid" | "soft") => void;
  notificationOccurred: (type: "error" | "success" | "warning") => void;
  selectionChanged: () => void;
}

// Bot API 6.9+ — `WebApp.CloudStorage`. Synced server-side by Telegram
// across all the user's clients. Keys: 1..128 chars `[A-Za-z0-9_-]+`,
// values up to 4096 chars, max 1024 entries. We use this for tiny UI
// state (last horizon, last category filter) so the app feels personal
// across phone, desktop, and tablet — no backend roundtrip.
interface TelegramCloudStorage {
  setItem: (
    key: string,
    value: string,
    callback?: (error: Error | null, stored: boolean) => void,
  ) => void;
  getItem: (key: string, callback: (error: Error | null, value: string) => void) => void;
  getItems: (
    keys: string[],
    callback: (error: Error | null, values: Record<string, string>) => void,
  ) => void;
  removeItem: (
    key: string,
    callback?: (error: Error | null, removed: boolean) => void,
  ) => void;
  removeItems: (
    keys: string[],
    callback?: (error: Error | null, removed: boolean) => void,
  ) => void;
  getKeys: (callback: (error: Error | null, keys: string[]) => void) => void;
}

export interface TelegramWebApp {
  initData: string;
  initDataUnsafe: {
    user?: {
      id: number;
      first_name: string;
      last_name?: string;
      username?: string;
    };
  };
  colorScheme: "light" | "dark";
  themeParams: TelegramThemeParams;
  isExpanded: boolean;
  version?: string;
  expand: () => void;
  ready: () => void;
  close: () => void;
  HapticFeedback: TelegramHapticFeedback;
  CloudStorage?: TelegramCloudStorage;
  onEvent: (event: string, callback: () => void) => void;
  offEvent: (event: string, callback: () => void) => void;
  showAlert?: (msg: string) => void;
  showConfirm?: (msg: string, cb: (ok: boolean) => void) => void;
}

declare global {
  interface Window {
    Telegram?: {
      WebApp?: TelegramWebApp;
    };
  }
}

export function getWebApp(): TelegramWebApp | null {
  return typeof window !== "undefined" ? (window.Telegram?.WebApp ?? null) : null;
}

/** Apply Telegram theme params to CSS variables on `:root`. */
export function applyTheme(): void {
  const wa = getWebApp();
  if (!wa) return;
  const root = document.documentElement;
  const map: Record<string, string | undefined> = {
    "--tg-theme-bg-color": wa.themeParams.bg_color,
    "--tg-theme-text-color": wa.themeParams.text_color,
    "--tg-theme-hint-color": wa.themeParams.hint_color,
    "--tg-theme-link-color": wa.themeParams.link_color,
    "--tg-theme-button-color": wa.themeParams.button_color,
    "--tg-theme-button-text-color": wa.themeParams.button_text_color,
    "--tg-theme-secondary-bg-color": wa.themeParams.secondary_bg_color,
    "--tg-theme-destructive-text-color": wa.themeParams.destructive_text_color,
    "--tg-theme-section-header-text-color": wa.themeParams.section_header_text_color,
    "--tg-theme-section-separator-color": wa.themeParams.section_separator_color,
  };
  for (const [name, value] of Object.entries(map)) {
    if (value) root.style.setProperty(name, value);
  }
  // Some Telegram clients only set `colorScheme` — make sure we always
  // produce visible text.
  if (wa.colorScheme === "dark") {
    root.classList.add("dark");
  } else {
    root.classList.remove("dark");
  }
}

export function bootTelegramWebApp(onThemeChange: () => void): void {
  const wa = getWebApp();
  if (!wa) return;
  applyTheme();
  wa.ready();
  if (!wa.isExpanded) {
    wa.expand();
  }
  wa.onEvent("themeChanged", () => {
    applyTheme();
    onThemeChange();
  });
}

export function haptic(kind: "select" | "success" | "error" | "warn" = "select"): void {
  const wa = getWebApp();
  if (!wa) return;
  try {
    if (kind === "select") wa.HapticFeedback.selectionChanged();
    else if (kind === "success") wa.HapticFeedback.notificationOccurred("success");
    else if (kind === "error") wa.HapticFeedback.notificationOccurred("error");
    else wa.HapticFeedback.notificationOccurred("warning");
  } catch {
    // Old WebApp versions don't expose HapticFeedback — fail silently.
  }
}
