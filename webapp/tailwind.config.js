/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Telegram theme variables (set by the WebApp client at runtime).
        // Tailwind references them via `var(--tg-*)` so the UI inherits
        // the user's chosen Telegram theme automatically.
        "tg-bg": "var(--tg-theme-bg-color, #ffffff)",
        "tg-secondary": "var(--tg-theme-secondary-bg-color, #f4f4f5)",
        "tg-text": "var(--tg-theme-text-color, #111827)",
        "tg-hint": "var(--tg-theme-hint-color, #6b7280)",
        "tg-link": "var(--tg-theme-link-color, #2563eb)",
        "tg-button": "var(--tg-theme-button-color, #2563eb)",
        "tg-button-text": "var(--tg-theme-button-text-color, #ffffff)",
        "tg-destructive": "var(--tg-theme-destructive-text-color, #dc2626)",
        "tg-section-header": "var(--tg-theme-section-header-text-color, #6b7280)",
        "tg-divider": "var(--tg-theme-section-separator-color, #e5e7eb)",
      },
    },
  },
  plugins: [],
};
