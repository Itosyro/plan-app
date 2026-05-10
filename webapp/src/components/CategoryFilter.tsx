import type { Category } from "../types";
import { haptic } from "../lib/telegram";

interface Props {
  categories: Category[];
  selectedId: number | null;
  onChange: (id: number | null) => void;
}

// Bento-style category pills. Matches the visual language of
// ``HorizonTabs`` (rounded-full, soft ring, font-display label,
// tabular count badge) but without per-category tone colors —
// categories are user-defined, so the active pill picks up the
// generic accent (Telegram button color) instead of a fixed palette.
export function CategoryFilter({ categories, selectedId, onChange }: Props) {
  if (categories.length === 0) return null;
  return (
    <div className="no-scrollbar mb-3 -mx-1 flex gap-1.5 overflow-x-auto px-1">
      <CategoryPill
        label="Все"
        count={null}
        active={selectedId === null}
        onClick={() => {
          haptic("select");
          onChange(null);
        }}
      />
      {categories.map((c) => {
        const active = c.id === selectedId;
        return (
          <CategoryPill
            key={c.id}
            label={c.name}
            count={c.task_count > 0 ? c.task_count : null}
            active={active}
            onClick={() => {
              haptic("select");
              onChange(active ? null : c.id);
            }}
          />
        );
      })}
    </div>
  );
}

interface PillProps {
  label: string;
  count: number | null;
  active: boolean;
  onClick: () => void;
}

function CategoryPill({ label, count, active, onClick }: PillProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        "ease-apple inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full px-3 py-1.5 text-[13px] font-medium transition-all duration-200 active:scale-[0.96] " +
        (active
          ? "bg-tg-button/10 text-tg-button shadow-bento ring-1 ring-tg-button/20"
          : "bg-bento-card text-tg-text/70 ring-1 ring-black/5 hover:text-tg-text")
      }
    >
      <span className="font-display tracking-tight">{label}</span>
      {count !== null && (
        <span
          className={
            "tabular inline-flex min-w-[18px] items-center justify-center rounded-full px-1.5 text-[11px] font-semibold " +
            (active ? "bg-bento-card/80 text-current" : "bg-bento text-tg-hint")
          }
        >
          {count}
        </span>
      )}
    </button>
  );
}
