import type { Horizon, TaskCounts } from "../types";
import { haptic } from "../lib/telegram";

// Caller passes either a fully-typed ``TaskCounts`` from the API or
// an empty ``Record<string, number>`` (e.g. test harness, fallback).
// Either way, we look up by string slug → number with a 0 default,
// so the badge silently disappears when a horizon has no open tasks.
type CountsLookup = TaskCounts | Record<string, number>;

interface Props {
  horizons: Horizon[];
  active: string;
  counts?: CountsLookup;
  onChange: (slug: string) => void;
}

export function HorizonTabs({ horizons, active, counts, onChange }: Props) {
  const lookup = counts as Record<string, number> | undefined;
  return (
    <div className="sticky top-0 z-10 -mx-4 mb-3 bg-tg-bg/90 px-4 pb-2 pt-1 backdrop-blur">
      <div className="no-scrollbar -mx-1 flex gap-1 overflow-x-auto px-1">
        {horizons.map((h) => {
          const isActive = h.slug === active;
          const count = lookup?.[h.slug] ?? 0;
          return (
            <button
              key={h.slug}
              type="button"
              onClick={() => {
                haptic("select");
                onChange(h.slug);
              }}
              className={
                "shrink-0 whitespace-nowrap rounded-full px-3 py-1.5 text-sm transition-colors " +
                (isActive
                  ? "bg-tg-button text-tg-button-text shadow-sm"
                  : "bg-tg-secondary text-tg-text/80 hover:bg-tg-secondary/80")
              }
            >
              <span>{h.label}</span>
              {count > 0 && (
                <span
                  className={
                    "ml-1.5 inline-block min-w-5 rounded-full px-1.5 text-xs " +
                    (isActive
                      ? "bg-tg-button-text/20 text-tg-button-text"
                      : "bg-tg-bg/60 text-tg-hint")
                  }
                >
                  {count}
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
