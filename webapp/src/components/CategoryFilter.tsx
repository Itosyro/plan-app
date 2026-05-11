import { Check } from "lucide-react";
import type { Category } from "../types";
import { haptic } from "../lib/telegram";
import { BottomSheet } from "./BottomSheet";

interface Props {
  open: boolean;
  onClose: () => void;
  categories: Category[];
  selectedId: number | null;
  onChange: (id: number | null) => void;
}

// Category picker rendered inside a BottomSheet, opened from the
// header's filter-icon button. Replaces the inline pill-rail that
// used to add a second row to every tasks screen.
//
// The list always starts with «Все» (clears the filter). Each row
// shows the category name on the left, an open-task count on the
// right, and a check mark when active.
export function CategoryFilter({
  open,
  onClose,
  categories,
  selectedId,
  onChange,
}: Props) {
  const hint =
    categories.length === 0
      ? "Категории появятся после первой задачи"
      : "Покажу только задачи в выбранной категории.";
  return (
    <BottomSheet open={open} onClose={onClose} title="Категория" hint={hint}>
      <ul role="listbox" aria-label="Категории" className="-mx-2 flex flex-col">
        <Row
          label="Все"
          count={null}
          active={selectedId === null}
          onClick={() => {
            haptic("select");
            onChange(null);
            onClose();
          }}
        />
        {categories.map((c) => (
          <Row
            key={c.id}
            label={c.name}
            count={c.task_count}
            active={c.id === selectedId}
            onClick={() => {
              haptic("select");
              onChange(c.id);
              onClose();
            }}
          />
        ))}
      </ul>
    </BottomSheet>
  );
}

interface RowProps {
  label: string;
  count: number | null;
  active: boolean;
  onClick: () => void;
}

function Row({ label, count, active, onClick }: RowProps) {
  return (
    <li role="presentation">
      <button
        type="button"
        role="option"
        aria-selected={active}
        onClick={onClick}
        className={
          "ease-apple flex w-full items-center justify-between gap-3 rounded-2xl px-3 py-3 text-left transition-all duration-200 active:scale-[0.99] " +
          (active ? "bg-tg-button/10" : "hover:bg-bento")
        }
      >
        <span className="min-w-0 flex-1">
          <span
            className={
              "font-display block truncate text-[16px] tracking-tight " +
              (active
                ? "font-semibold text-tg-button"
                : "font-medium text-tg-text")
            }
          >
            {label}
          </span>
        </span>
        {count !== null && count > 0 && (
          <span
            className={
              "tabular inline-flex min-w-[20px] items-center justify-center rounded-full px-1.5 text-[12px] font-semibold " +
              (active
                ? "bg-tg-button/15 text-tg-button"
                : "bg-bento text-tg-hint")
            }
          >
            {count}
          </span>
        )}
        {active && (
          <Check
            size={20}
            strokeWidth={2.5}
            className="shrink-0 text-tg-button"
            aria-hidden
          />
        )}
      </button>
    </li>
  );
}
