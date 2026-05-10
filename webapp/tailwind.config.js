/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        // Single Inter Variable family driven by the opsz axis. Apply
        // ``font-display`` utility for big headings (sets opsz=32);
        // body text picks up opsz=auto so 14–18px sizes use Inter
        // Text proportions. See ``index.css``.
        sans: [
          '"Inter Variable"',
          "-apple-system",
          "BlinkMacSystemFont",
          '"SF Pro Text"',
          '"Segoe UI"',
          "Roboto",
          '"Helvetica Neue"',
          "sans-serif",
        ],
      },
      colors: {
        // Telegram theme variables (set by the WebApp client at runtime).
        // Tailwind references them via `var(--tg-*)` so the UI inherits
        // the user's chosen Telegram theme automatically.
        "tg-bg": "var(--tg-theme-bg-color, #ffffff)",
        "tg-secondary": "var(--tg-theme-secondary-bg-color, #f2f2f7)",
        "tg-text": "var(--tg-theme-text-color, #0f172a)",
        "tg-hint": "var(--tg-theme-hint-color, #8e8e93)",
        "tg-link": "var(--tg-theme-link-color, #2563eb)",
        "tg-button": "var(--tg-theme-button-color, #2563eb)",
        "tg-button-text": "var(--tg-theme-button-text-color, #ffffff)",
        "tg-destructive": "var(--tg-theme-destructive-text-color, #dc2626)",
        "tg-section-header": "var(--tg-theme-section-header-text-color, #6b7280)",
        "tg-divider": "var(--tg-theme-section-separator-color, #e5e7eb)",

        // Bento page background + card surface. Resolved at runtime
        // from Telegram theme params (see index.css).
        bento: "var(--bento-bg, #f2f2f7)",
        "bento-card": "var(--bento-card, #ffffff)",
      },
      borderRadius: {
        // iOS-style "continuous" rounding. We use 18-28px on cards
        // (Apple uses 22 for cards, 16 for inner controls).
        "2.5xl": "1.25rem",  // 20px
        "4xl": "1.75rem",    // 28px
      },
      boxShadow: {
        // Apple-style elevations: very tight, very low alpha. The
        // shadow exists to lift a card off the bento background, not
        // to dramatize.
        "bento": "0 1px 2px 0 rgb(0 0 0 / 0.04), 0 1px 3px 0 rgb(0 0 0 / 0.06)",
        "bento-lg": "0 4px 16px 0 rgb(0 0 0 / 0.06), 0 2px 4px 0 rgb(0 0 0 / 0.04)",
        "island": "0 8px 24px -4px rgb(0 0 0 / 0.12), 0 4px 8px -2px rgb(0 0 0 / 0.06)",
      },
    },
  },
  plugins: [],
};
