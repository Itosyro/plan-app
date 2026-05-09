import type { Category } from "../types";
import { haptic } from "../lib/telegram";

interface Props {
  categories: Category[];
  selectedId: number | null;
  onChange: (id: number | null) => void;
}

export function CategoryFilter({ categories, selectedId, onChange }: Props) {
  if (categories.length === 0) return null;
  return (
    <div className="no-scrollbar mb-3 flex gap-2 overflow-x-auto">
      <button
        type="button"
        onClick={() => {
          haptic("select");
          onChange(null);
        }}
        className={
          "shrink-0 rounded-full border px-3 py-1 text-sm " +
          (selectedId === null
            ? "border-tg-button bg-tg-button/10 text-tg-button"
            : "border-tg-divider bg-tg-bg text-tg-hint")
        }
      >
        Все
      </button>
      {categories.map((c) => {
        const active = c.id === selectedId;
        return (
          <button
            key={c.id}
            type="button"
            onClick={() => {
              haptic("select");
              onChange(active ? null : c.id);
            }}
            className={
              "shrink-0 rounded-full border px-3 py-1 text-sm " +
              (active
                ? "border-tg-button bg-tg-button/10 text-tg-button"
                : "border-tg-divider bg-tg-bg text-tg-text/80")
            }
          >
            <span>{c.name}</span>
            {c.task_count > 0 && (
              <span className="ml-1.5 text-xs text-tg-hint">{c.task_count}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}
