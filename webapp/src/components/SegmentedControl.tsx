// Reusable iOS / Telegram-style segmented control. A pill-shaped track
// (``bg-bento``) with a single sliding capsule behind the active
// segment — the capsule animates left/right via ``translateX`` instead
// of swapping background colors, so switching reads as one continuous
// motion (same trick as BottomNav, #109).
//
// Segments are equal-width flex cells. The capsule width is
// ``(100% - track padding) / n`` and it slides by ``index * 100%`` of
// its own width — with no gaps between cells this lands it exactly over
// the active segment regardless of how many options there are.
//
// Used for the Tasks List/Board toggle and the Calendar month/week/day
// modes. Touch targets are ≥44px tall in the default size.

import type { LucideIcon } from "lucide-react";
import { haptic } from "../lib/telegram";

export interface SegmentOption<T extends string> {
  value: T;
  label: string;
  icon?: LucideIcon;
}

interface Props<T extends string> {
  options: SegmentOption<T>[];
  value: T;
  onChange: (value: T) => void;
  /** ``md`` (default) is ≥44px tall; ``sm`` is compact for dense headers. */
  size?: "sm" | "md";
  ariaLabel?: string;
  className?: string;
}

export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  size = "md",
  ariaLabel,
  className = "",
}: Props<T>) {
  const activeIndex = Math.max(
    0,
    options.findIndex((o) => o.value === value),
  );
  const n = options.length;
  const sized = size === "md" ? "min-h-[44px] text-[14px]" : "min-h-[36px] text-[13px]";

  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      className={
        "relative flex rounded-2xl bg-bento p-1 ring-1 ring-tg-divider/30 " + className
      }
    >
      {/* Sliding active capsule. Width matches one segment; translateX
          moves it by whole-segment steps. cubic-bezier = soft iOS spring. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-y-1 left-1 rounded-xl bg-bento-card shadow-bento ring-1 ring-tg-divider/30"
        style={{
          width: `calc((100% - 0.5rem) / ${n})`,
          transform: `translateX(${activeIndex * 100}%)`,
          transition: "transform 300ms cubic-bezier(0.32, 0.72, 0.20, 1.05)",
        }}
      />
      {options.map((opt) => {
        const active = opt.value === value;
        const Icon = opt.icon;
        return (
          <button
            key={opt.value}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => {
              if (active) return;
              haptic("select");
              onChange(opt.value);
            }}
            className={
              "relative z-10 flex flex-1 items-center justify-center gap-1.5 rounded-xl font-medium tracking-tight transition-colors duration-200 active:scale-[0.97] " +
              sized +
              " " +
              (active
                ? "font-semibold text-tg-text"
                : "text-tg-hint hover:text-tg-text")
            }
          >
            {Icon && (
              <Icon
                size={size === "md" ? 16 : 15}
                strokeWidth={active ? 2.4 : 2.0}
                aria-hidden
              />
            )}
            <span>{opt.label}</span>
          </button>
        );
      })}
    </div>
  );
}
