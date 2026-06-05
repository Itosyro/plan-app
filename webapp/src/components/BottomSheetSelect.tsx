// iOS-style single-select picker rendered inside a BottomSheet.
// Replaces native ``<select>`` elements, which look like Material
// dropdowns on Android and don't honor our font / theme.
//
// Each option is a full-width *card* — not a flat row — so it reads
// unmistakably as a tappable control: ``bg-bento`` surface, hairline
// ring, ≥44px height, a clear hover lift and ``active:scale``. The
// selected option fills with the accent tint, switches its label to
// the accent color + semibold and shows a check on the right.
// Rows cascade in with a small staggered slide-up on open.

import { Check } from "lucide-react";
import { haptic } from "../lib/telegram";
import { BottomSheet } from "./BottomSheet";

interface Option {
  value: string;
  label: string;
  hint?: string;
}

interface Props {
  open: boolean;
  onClose: () => void;
  title: string;
  hint?: string;
  options: Option[];
  value: string;
  onSelect: (value: string) => void;
}

export function BottomSheetSelect({
  open,
  onClose,
  title,
  hint,
  options,
  value,
  onSelect,
}: Props) {
  return (
    <BottomSheet open={open} onClose={onClose} title={title} hint={hint}>
      <ul role="listbox" aria-label={title} className="flex flex-col gap-2 pb-1">
        {options.map((opt, idx) => {
          const active = opt.value === value;
          return (
            <li key={opt.value} role="presentation">
              <button
                type="button"
                role="option"
                aria-selected={active}
                onClick={() => {
                  haptic("select");
                  onSelect(opt.value);
                  onClose();
                }}
                style={{
                  animation: "sheet-row-in 260ms cubic-bezier(0.16, 1, 0.3, 1) both",
                  animationDelay: `${idx * 35}ms`,
                }}
                className={
                  "ease-apple flex w-full items-center justify-between gap-3 rounded-2xl px-4 py-3 text-left ring-1 transition-all duration-200 active:scale-[0.98] " +
                  (active
                    ? "bg-tg-button/10 ring-tg-button/30"
                    : "bg-bento ring-tg-divider/30 hover:bg-tg-button/[0.06] hover:ring-tg-divider/50")
                }
              >
                <span className="min-w-0">
                  <span
                    className={
                      "font-display block text-[16px] tracking-tight " +
                      (active
                        ? "font-semibold text-tg-button"
                        : "font-medium text-tg-text")
                    }
                  >
                    {opt.label}
                  </span>
                  {opt.hint && (
                    <span className="mt-0.5 block text-[12px] leading-snug text-tg-hint">
                      {opt.hint}
                    </span>
                  )}
                </span>
                <span
                  aria-hidden
                  className={
                    "flex h-6 w-6 shrink-0 items-center justify-center rounded-full transition-all duration-200 " +
                    (active
                      ? "bg-tg-button text-tg-button-text scale-100"
                      : "scale-0")
                  }
                >
                  <Check size={15} strokeWidth={3} />
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </BottomSheet>
  );
}
