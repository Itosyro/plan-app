// Phase 7e/F1+F2: «Раскладка» bottom-sheet — the Todoist-style layout
// popover, our Telegram-native take. Holds the view switch (replaces
// the standalone inline ViewToggle), a "show completed" toggle, and the
// list grouping / sorting / filtering controls (F2).

import { LayoutGrid, ListTodo } from "lucide-react";
import { BottomSheet } from "./BottomSheet";
import { SegmentedControl, type SegmentOption } from "./SegmentedControl";
import { Switch } from "./Switch";
import { haptic } from "../lib/telegram";
import type {
  FilterDue,
  FilterPriority,
  GroupBy,
  SortBy,
} from "../lib/layoutPrefs";

const VIEW_OPTIONS: SegmentOption<"list" | "board">[] = [
  { value: "list", label: "Список", icon: ListTodo },
  { value: "board", label: "Доска", icon: LayoutGrid },
];

const GROUP_OPTIONS: { value: GroupBy; label: string }[] = [
  { value: "none", label: "Без группировки" },
  { value: "category", label: "По разделу" },
  { value: "priority", label: "По приоритету" },
  { value: "horizon", label: "По горизонту" },
];

const SORT_OPTIONS: { value: SortBy; label: string }[] = [
  { value: "manual", label: "Вручную" },
  { value: "date", label: "По дате" },
  { value: "priority", label: "По приоритету" },
  { value: "alpha", label: "По алфавиту" },
];

const PRIORITY_OPTIONS: { value: FilterPriority; label: string }[] = [
  { value: "all", label: "Любой" },
  { value: "high", label: "Высокий" },
  { value: "medium", label: "Средний" },
  { value: "low", label: "Низкий" },
];

const DUE_OPTIONS: { value: FilterDue; label: string }[] = [
  { value: "all", label: "Все" },
  { value: "overdue", label: "Просроченные" },
  { value: "today", label: "Сегодня" },
  { value: "week", label: "7 дней" },
];

// Compact wrap-grid of option chips — denser than BottomSheetSelect (which
// is its own sheet) and consistent with the sheet's bento look. The active
// chip fills with the accent tint, matching BottomSheetSelect.
function OptionGroup<T extends string>({
  ariaLabel,
  options,
  value,
  onChange,
}: {
  ariaLabel: string;
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div
      role="group"
      aria-label={ariaLabel}
      className="flex flex-wrap gap-2"
    >
      {options.map((opt) => {
        const active = opt.value === value;
        return (
          <button
            key={opt.value}
            type="button"
            aria-pressed={active}
            onClick={() => {
              if (active) return;
              haptic("select");
              onChange(opt.value);
            }}
            className={
              "ease-apple rounded-2xl px-3.5 py-2 text-[14px] font-medium tracking-tight ring-1 transition-all duration-200 active:scale-[0.97] " +
              (active
                ? "bg-tg-button/10 font-semibold text-tg-button ring-tg-button/30"
                : "bg-bento text-tg-text ring-tg-divider/30 hover:bg-tg-button/[0.06] hover:ring-tg-divider/50")
            }
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}

interface Props {
  open: boolean;
  onClose: () => void;
  view: "list" | "board";
  onViewChange: (v: "list" | "board") => void;
  showCompleted: boolean;
  onShowCompletedChange: (next: boolean) => void;
  // Phase 7e/F2: list grouping / sorting / filtering.
  groupBy: GroupBy;
  onGroupByChange: (v: GroupBy) => void;
  sortBy: SortBy;
  onSortByChange: (v: SortBy) => void;
  filterPriority: FilterPriority;
  onFilterPriorityChange: (v: FilterPriority) => void;
  filterDue: FilterDue;
  onFilterDueChange: (v: FilterDue) => void;
  onResetAll: () => void;
}

const HEADER_CLS =
  "mb-2 text-[13px] font-semibold tracking-tight text-tg-link";

export function LayoutSheet({
  open,
  onClose,
  view,
  onViewChange,
  showCompleted,
  onShowCompletedChange,
  groupBy,
  onGroupByChange,
  sortBy,
  onSortByChange,
  filterPriority,
  onFilterPriorityChange,
  filterDue,
  onFilterDueChange,
  onResetAll,
}: Props) {
  // Grouping / sorting / filtering only make sense for the list view.
  const showListControls = view === "list";

  return (
    <BottomSheet open={open} onClose={onClose} title="Раскладка">
      <div className="flex flex-col gap-5 pb-1">
        <section>
          <header className={HEADER_CLS}>Вид</header>
          <SegmentedControl
            ariaLabel="Вид задач"
            options={VIEW_OPTIONS}
            value={view}
            onChange={onViewChange}
          />
        </section>

        <section>
          <header className={HEADER_CLS}>Задачи</header>
          <button
            type="button"
            onClick={() => onShowCompletedChange(!showCompleted)}
            aria-pressed={showCompleted}
            className="ease-apple flex min-h-[52px] w-full items-center justify-between gap-3 rounded-2xl bg-bento px-4 py-3 text-left ring-1 ring-tg-divider/30 transition-colors duration-150 active:bg-bento/70"
          >
            <span className="min-w-0">
              <span className="block text-[15px] font-medium text-tg-text">
                Показывать выполненные
              </span>
              <span className="mt-0.5 block text-[12px] leading-snug text-tg-hint">
                Завершённые задачи остаются в списке зачёркнутыми
              </span>
            </span>
            <Switch checked={showCompleted} presentational />
          </button>
        </section>

        {showListControls && (
          <>
            <section>
              <header className={HEADER_CLS}>Группировка</header>
              <OptionGroup
                ariaLabel="Группировка задач"
                options={GROUP_OPTIONS}
                value={groupBy}
                onChange={onGroupByChange}
              />
            </section>

            <section>
              <header className={HEADER_CLS}>Сортировка</header>
              <OptionGroup
                ariaLabel="Сортировка задач"
                options={SORT_OPTIONS}
                value={sortBy}
                onChange={onSortByChange}
              />
            </section>

            <section>
              <header className={HEADER_CLS}>Фильтр</header>
              <div className="flex flex-col gap-3">
                <div>
                  <span className="mb-1.5 block text-[12px] font-medium text-tg-hint">
                    Приоритет
                  </span>
                  <OptionGroup
                    ariaLabel="Фильтр по приоритету"
                    options={PRIORITY_OPTIONS}
                    value={filterPriority}
                    onChange={onFilterPriorityChange}
                  />
                </div>
                <div>
                  <span className="mb-1.5 block text-[12px] font-medium text-tg-hint">
                    Срок
                  </span>
                  <OptionGroup
                    ariaLabel="Фильтр по сроку"
                    options={DUE_OPTIONS}
                    value={filterDue}
                    onChange={onFilterDueChange}
                  />
                </div>
              </div>
            </section>

            <button
              type="button"
              onClick={() => {
                haptic("select");
                onResetAll();
              }}
              className="ease-apple self-center rounded-xl px-4 py-2 text-[14px] font-medium text-tg-link transition-colors duration-150 active:opacity-60"
            >
              Сбросить всё
            </button>
          </>
        )}
      </div>
    </BottomSheet>
  );
}
