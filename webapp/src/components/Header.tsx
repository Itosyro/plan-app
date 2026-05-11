import { SlidersHorizontal } from "lucide-react";
import type { Horizon, TaskCounts } from "../types";

interface Props {
  /**
   * Resolved big-title for the current view (e.g. «Сегодня • 3 задачи»).
   * The parent computes it from active horizon + counts so the header
   * stays presentational.
   */
  title: string;
  /** Soft subtitle line, e.g. greeting or category filter status. */
  subtitle?: string;
  /** Active horizon slug so the filter button can hide on settings. */
  showFilter?: boolean;
  /** Currently selected category id, ``null`` = «Все». */
  selectedCategoryId?: number | null;
  /** Click on filter chip → open the category bottom-sheet. */
  onOpenFilter?: () => void;
  /** Optional filter button label override. */
  filterLabel?: string;
}

// Bento-page header. One display title, optional subtitle, and a
// single filter-icon button on the right. The horizons rail and
// category picker that used to clutter this row have moved:
//   • Horizons → ``HorizonTabs`` (scroll-snap rail below).
//   • Category → bottom-sheet, opened from the filter button.
export function Header({
  title,
  subtitle,
  showFilter = true,
  selectedCategoryId = null,
  onOpenFilter,
  filterLabel,
}: Props) {
  const hasActiveFilter = selectedCategoryId !== null;
  return (
    <header className="mb-3 flex items-end justify-between gap-3">
      <div className="min-w-0">
        <h1 className="font-display truncate text-[28px] font-semibold leading-tight tracking-tight text-tg-text">
          {title}
        </h1>
        {subtitle && (
          <p className="mt-0.5 truncate text-[13px] text-tg-hint">{subtitle}</p>
        )}
      </div>
      {showFilter && onOpenFilter && (
        <button
          type="button"
          onClick={onOpenFilter}
          aria-label={filterLabel ?? "Категории"}
          className={
            "ease-apple inline-flex h-10 shrink-0 items-center gap-1.5 rounded-2xl px-3 text-[13px] font-medium transition-all duration-200 active:scale-[0.96] " +
            (hasActiveFilter
              ? "bg-tg-button/10 text-tg-button ring-1 ring-tg-button/20"
              : "bg-bento-card text-tg-text/70 ring-1 ring-black/5 hover:text-tg-text")
          }
        >
          <SlidersHorizontal size={16} strokeWidth={2.25} aria-hidden />
          {hasActiveFilter && filterLabel && (
            <span className="font-display max-w-[120px] truncate tracking-tight">
              {filterLabel}
            </span>
          )}
        </button>
      )}
    </header>
  );
}

// Helper used by App.tsx to build the big title from horizons + counts.
export function buildHeaderTitle(
  horizons: Horizon[],
  active: string,
  counts: TaskCounts | undefined,
): string {
  const hit = horizons.find((h) => h.slug === active);
  const base = hit?.label ?? "План";
  if (counts === undefined) return base;
  const n = (counts as unknown as Record<string, number>)[active];
  if (typeof n !== "number" || n <= 0) return base;
  return `${base} • ${formatTaskCount(n)}`;
}

function formatTaskCount(n: number): string {
  // Cheap Russian pluralization for "задача / задачи / задач".
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 14) return `${n} задач`;
  if (mod10 === 1) return `${n} задача`;
  if (mod10 >= 2 && mod10 <= 4) return `${n} задачи`;
  return `${n} задач`;
}


