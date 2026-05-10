import { useDroppable } from "@dnd-kit/core";
import type { Horizon, HorizonSlug, TaskCounts } from "../types";
import { horizonIcon } from "../lib/icons";
import { haptic } from "../lib/telegram";
import type { TileTone } from "./IconTile";

// Caller passes either a fully-typed ``TaskCounts`` from the API or
// an empty ``Record<string, number>`` (e.g. test harness, fallback).
type CountsLookup = TaskCounts | Record<string, number>;

interface Props {
  horizons: Horizon[];
  active: string;
  counts?: CountsLookup;
  onChange: (slug: string) => void;
}

// Per-horizon tone — picks the colored "tile" behind each pill's
// icon when the pill is active. Stays predictable across screens
// (settings rows, future calendar) so the user learns the colors.
const HORIZON_TONE: Record<HorizonSlug, TileTone> = {
  today: "orange",
  tomorrow: "amber",
  week: "violet",
  month: "indigo",
  year: "blue",
  someday: "slate",
};

const TONE_BG: Record<TileTone, string> = {
  violet: "bg-violet-500/10 text-violet-700",
  indigo: "bg-indigo-500/10 text-indigo-700",
  blue: "bg-blue-500/10 text-blue-700",
  sky: "bg-sky-500/10 text-sky-700",
  teal: "bg-teal-500/10 text-teal-700",
  emerald: "bg-emerald-500/10 text-emerald-700",
  amber: "bg-amber-500/15 text-amber-800",
  orange: "bg-orange-500/15 text-orange-700",
  rose: "bg-rose-500/10 text-rose-700",
  pink: "bg-pink-500/10 text-pink-700",
  slate: "bg-slate-500/10 text-slate-700",
};

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
  const tone = HORIZON_TONE[horizon.slug as HorizonSlug] ?? "slate";
  const toneClass = TONE_BG[tone];

  return (
    <button
      ref={setNodeRef}
      type="button"
      onClick={() => {
        haptic("select");
        onChange(horizon.slug);
      }}
      className={
        "ease-apple inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full px-3 py-1.5 text-[13px] font-medium transition-all duration-200 active:scale-[0.96] " +
        (isActive
          ? toneClass + " shadow-bento ring-1 ring-black/5"
          : "bg-bento-card text-tg-text/70 ring-1 ring-black/5 hover:text-tg-text") +
        (isOver ? " ring-2 ring-tg-button ring-offset-2 ring-offset-bento" : "")
      }
    >
      <Icon size={15} strokeWidth={2.25} aria-hidden />
      <span className="font-display tracking-tight">{horizon.label}</span>
      {count > 0 && (
        <span
          className={
            "tabular ml-0.5 inline-flex min-w-[18px] items-center justify-center rounded-full px-1.5 text-[11px] font-semibold " +
            (isActive
              ? "bg-bento-card/80 text-current"
              : "bg-bento text-tg-hint")
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
    <div className="sticky top-0 z-10 -mx-4 mb-3 bg-bento/85 px-4 pb-2 pt-1 backdrop-blur-xl">
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
