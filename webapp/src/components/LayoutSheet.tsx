// Phase 7e/F1: «Раскладка» bottom-sheet — the Todoist-style layout
// popover, our Telegram-native take. Holds the view switch (replaces
// the standalone inline ViewToggle) and a "show completed" toggle.
// Grouping / sorting / filtering land here later (F2).

import { LayoutGrid, ListTodo } from "lucide-react";
import { BottomSheet } from "./BottomSheet";
import { SegmentedControl, type SegmentOption } from "./SegmentedControl";
import { Switch } from "./Switch";

const VIEW_OPTIONS: SegmentOption<"list" | "board">[] = [
  { value: "list", label: "Список", icon: ListTodo },
  { value: "board", label: "Доска", icon: LayoutGrid },
];

interface Props {
  open: boolean;
  onClose: () => void;
  view: "list" | "board";
  onViewChange: (v: "list" | "board") => void;
  showCompleted: boolean;
  onShowCompletedChange: (next: boolean) => void;
}

export function LayoutSheet({
  open,
  onClose,
  view,
  onViewChange,
  showCompleted,
  onShowCompletedChange,
}: Props) {
  return (
    <BottomSheet open={open} onClose={onClose} title="Раскладка">
      <div className="flex flex-col gap-5 pb-1">
        <section>
          <header className="mb-2 text-[13px] font-semibold tracking-tight text-tg-link">
            Вид
          </header>
          <SegmentedControl
            ariaLabel="Вид задач"
            options={VIEW_OPTIONS}
            value={view}
            onChange={onViewChange}
          />
        </section>

        <section>
          <header className="mb-2 text-[13px] font-semibold tracking-tight text-tg-link">
            Задачи
          </header>
          <button
            type="button"
            onClick={() => onShowCompletedChange(!showCompleted)}
            aria-pressed={showCompleted}
            className="ease-apple flex min-h-[52px] w-full items-center justify-between gap-3 rounded-2xl bg-bento px-4 py-3 text-left ring-1 ring-black/[0.04] transition-colors duration-150 active:bg-bento/70"
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
      </div>
    </BottomSheet>
  );
}
