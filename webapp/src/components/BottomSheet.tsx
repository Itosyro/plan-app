// Reusable bottom-sheet primitive. Renders a backdrop + a rounded
// card glued to the bottom of the viewport, with a grabber handle
// at the top and ``--safe-bottom`` padding so the close button
// never tucks under the iPhone home indicator.
//
// Animation: backdrop fades in (200 ms), sheet slides up from
// ``translateY(100%)`` to ``0`` with the Apple spring curve. The
// sheet is mounted only while ``open`` is true so React doesn't
// hold focus traps / scroll locks on closed sheets.
//
// Behaviour:
//   - Click on the backdrop closes the sheet.
//   - Escape key closes the sheet (focused inside or out — we
//     attach the listener while open).
//   - Body scroll is locked while open so the page underneath
//     doesn't bounce on iOS.
//   - The first focusable inside is auto-focused for keyboard
//     users (mobile users see no caret, which is fine).

import { useEffect, useRef } from "react";
import { X } from "lucide-react";

interface Props {
  open: boolean;
  onClose: () => void;
  title: string;
  /** Optional secondary line shown under the title. */
  hint?: string;
  /** Render-prop children. */
  children: React.ReactNode;
  /**
   * Optional footer node. Pinned to the bottom with --safe-bottom
   * padding. Use it for Готово / Отмена buttons.
   */
  footer?: React.ReactNode;
}

export function BottomSheet({ open, onClose, title, hint, children, footer }: Props) {
  const sheetRef = useRef<HTMLDivElement | null>(null);

  // Lock body scroll while open. The Mini-App container itself is
  // a scrolling div, so we use ``overflow: hidden`` on the document
  // element which Telegram WebView honors.
  useEffect(() => {
    if (!open) return;
    const previous = document.documentElement.style.overflow;
    document.documentElement.style.overflow = "hidden";
    return () => {
      document.documentElement.style.overflow = previous;
    };
  }, [open]);

  // Escape-to-close. Attached only while open so other sheets don't
  // race against each other.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
    };
  }, [open, onClose]);

  // Auto-focus the first focusable inside the sheet. The actual
  // focus trap is intentionally lightweight — we rely on the
  // overlay capturing pointer events outside.
  useEffect(() => {
    if (!open) return;
    const sheet = sheetRef.current;
    if (sheet === null) return;
    const focusable = sheet.querySelector<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
    );
    focusable?.focus();
  }, [open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center">
      <div
        aria-hidden
        onClick={onClose}
        className="absolute inset-0 bg-black/40 backdrop-blur-sm"
        style={{ animation: "fade-in 150ms ease-out" }}
      />
      <div
        ref={sheetRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="relative z-10 w-full max-w-md rounded-t-3xl bg-bento-card text-tg-text shadow-bento-lg ring-1 ring-black/5"
        style={{
          animation: "slide-up 250ms cubic-bezier(0.16, 1, 0.3, 1)",
        }}
      >
        {/* Grabber */}
        <div className="flex justify-center pt-2">
          <span className="block h-1.5 w-10 rounded-full bg-tg-hint/30" aria-hidden />
        </div>
        {/* Header */}
        <header className="flex items-start justify-between gap-3 px-5 pb-3 pt-3">
          <div className="min-w-0">
            <h2 className="font-display truncate text-[17px] font-semibold tracking-tight text-tg-text">
              {title}
            </h2>
            {hint && (
              <p className="mt-0.5 truncate text-[12px] text-tg-hint">{hint}</p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Закрыть"
            className="ease-apple -mr-2 -mt-1 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-tg-hint transition-all duration-200 hover:bg-bento active:scale-[0.95]"
          >
            <X size={20} strokeWidth={2.25} aria-hidden />
          </button>
        </header>
        <div className="max-h-[60vh] overflow-y-auto px-5 pb-4">{children}</div>
        {footer && (
          <div
            className="border-t border-tg-divider/40 bg-bento-card px-5 pb-2 pt-3"
            style={{ paddingBottom: "calc(var(--safe-bottom) + 0.75rem)" }}
          >
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}
