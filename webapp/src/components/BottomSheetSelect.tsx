// iOS-style single-select picker rendered inside a BottomSheet.
// Replaces native ``<select>`` elements, which look like Material
// dropdowns on Android and don't honor our font / theme.
//
// Each option is a full-width row with a check on the right when
// active, large touch targets (44 px min height) and a subtle
// divider between rows. Selection commits on click + closes the
// sheet, matching iOS Settings.

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
  options: Option[];
  value: string;
  onSelect: (value: string) => void;
}

export function BottomSheetSelect({
  open,
  onClose,
  title,
  options,
  value,
  onSelect,
}: Props) {
  return (
    <BottomSheet open={open} onClose={onClose} title={title}>
      <ul role="listbox" aria-label={title} className="-mx-2 flex flex-col">
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
                className={
                  "ease-apple flex w-full items-center justify-between gap-3 rounded-2xl px-3 py-3 text-left transition-all duration-200 active:scale-[0.99] " +
                  (active ? "bg-tg-button/10" : "hover:bg-bento")
                }
              >
                <span className="min-w-0">
                  <span
                    className={
                      "font-display block truncate text-[16px] tracking-tight " +
                      (active
                        ? "font-semibold text-tg-button"
                        : "font-medium text-tg-text")
                    }
                  >
                    {opt.label}
                  </span>
                  {opt.hint && (
                    <span className="mt-0.5 block truncate text-[12px] text-tg-hint">
                      {opt.hint}
                    </span>
                  )}
                </span>
                {active && (
                  <Check
                    size={20}
                    strokeWidth={2.5}
                    className="shrink-0 text-tg-button"
                    aria-hidden
                  />
                )}
              </button>
              {idx < options.length - 1 && (
                <div
                  aria-hidden
                  className="mx-3 h-px bg-tg-divider/30 last:hidden"
                />
              )}
            </li>
          );
        })}
      </ul>
    </BottomSheet>
  );
}
