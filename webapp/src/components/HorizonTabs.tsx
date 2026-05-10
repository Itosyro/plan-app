import { useDroppable } from "@dnd-kit/core";
import type { Horizon, TaskCounts } from "../types";
import { horizonIcon } from "../lib/icons";
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

interface PillProps {
  horizon: Horizon;
  isActive: boolean;
  count: number;
  onChange: (slug: string) => void;
}

// Each pill is its own component so it can register a separate
// ``useDroppable`` ref. Phase 5.4b: dropping a TaskCard on a pill
// moves the task to that horizon (handled in App.tsx::onDragEnd).
function HorizonPill({ horizon, isActive, count, onChange }: PillProps) {
  const { isOver, setNodeRef } = useDroppable({ id: horizon.slug });
  const Icon = horizonIcon(horizon.slug);
  return (
    <button
      ref={setNodeRef}
      type="button"
      onClick={() => {
        haptic("select");
        onChange(horizon.slug);
      }}
      className={
        "inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full px-3 py-1.5 text-sm font-medium transition-colors " +
        (isActive
          ? "bg-tg-text text-tg-bg "
          : "bg-tg-secondary/60 text-tg-text/75 hover:bg-tg-secondary ") +
        (isOver ? "ring-2 ring-tg-button ring-offset-2 ring-offset-tg-bg " : "")
      }
    >
      <Icon size={15} strokeWidth={2} aria-hidden />
      <span>{horizon.label}</span>
      {count > 0 && (
        <span
          className={
            "ml-0.5 inline-flex min-w-[18px] items-center justify-center rounded-full px-1.5 text-[11px] font-semibold tabular-nums " +
            (isActive ? "bg-tg-bg/20 text-tg-bg" : "bg-tg-bg text-tg-hint")
          }
        >
          {count}
        </span>
      )}
    </button>
  );
}

export function HorizonTabs({ horizons, active, counts, onChange }: Props) {
  const lookup = counts as Record<string, number> | undefined;
  return (
    <div className="sticky top-0 z-10 -mx-4 mb-3 bg-tg-bg/95 px-4 pb-2 pt-1 backdrop-blur">
      <div className="no-scrollbar -mx-1 flex gap-1.5 overflow-x-auto px-1">
        {horizons.map((h) => (
          <HorizonPill
            key={h.slug}
            horizon={h}
            isActive={h.slug === active}
            count={lookup?.[h.slug] ?? 0}
            onChange={onChange}
          />
        ))}
      </div>
    </div>
  );
}
