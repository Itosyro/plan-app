import { useState } from "react";
import type { HorizonSlug, Task } from "../types";
import { formatDue, priorityIcon } from "../lib/format";
import { haptic } from "../lib/telegram";

const HORIZON_OPTIONS: { slug: HorizonSlug; label: string }[] = [
  { slug: "today", label: "Сегодня" },
  { slug: "tomorrow", label: "Завтра" },
  { slug: "week", label: "На неделе" },
  { slug: "month", label: "В месяце" },
  { slug: "year", label: "В году" },
  { slug: "someday", label: "Когда-нибудь" },
];

interface Props {
  task: Task;
  tz: string;
  onDone: (id: number) => Promise<void> | void;
  onMove: (id: number, slug: HorizonSlug) => Promise<void> | void;
  onDelete: (id: number) => Promise<void> | void;
}

export function TaskCard({ task, tz, onDone, onMove, onDelete }: Props) {
  const [busy, setBusy] = useState(false);
  const [moveOpen, setMoveOpen] = useState(false);
  const due = formatDue(task.due_at, tz);
  const isDone = task.status === "done";

  const wrap = async (fn: () => Promise<void> | void) => {
    if (busy) return;
    setBusy(true);
    try {
      await fn();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className={
        "rounded-xl border border-tg-divider bg-tg-bg p-3 shadow-sm transition-opacity " +
        (isDone ? "opacity-50" : "opacity-100")
      }
    >
      <div className="flex items-start gap-3">
        <button
          type="button"
          aria-label={isDone ? "Готово" : "Отметить выполненной"}
          disabled={busy || isDone}
          onClick={() =>
            wrap(async () => {
              haptic("success");
              await onDone(task.id);
            })
          }
          className={
            "mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border " +
            (isDone
              ? "border-tg-button bg-tg-button text-tg-button-text"
              : "border-tg-hint hover:border-tg-button")
          }
        >
          {isDone ? "✓" : ""}
        </button>
        <div className="flex-1 min-w-0">
          <div
            className={
              "break-words text-base leading-snug " +
              (isDone ? "text-tg-hint line-through" : "text-tg-text")
            }
          >
            <span className="mr-1.5">{priorityIcon(task.priority)}</span>
            {task.title}
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-tg-hint">
            {due && <span>📅 {due}</span>}
            {task.category_name && (
              <span className="rounded-full bg-tg-secondary px-2 py-0.5">
                {task.category_name}
              </span>
            )}
            {task.horizon_slug && task.horizon_slug !== "today" && (
              <span className="text-tg-hint">{task.horizon_slug}</span>
            )}
          </div>
        </div>
      </div>
      {!isDone && (
        <div className="mt-3 flex items-center gap-2 border-t border-tg-divider pt-2">
          <button
            type="button"
            disabled={busy}
            onClick={() => setMoveOpen((v) => !v)}
            className="rounded-md px-2 py-1 text-xs text-tg-link hover:bg-tg-secondary"
          >
            🔄 Перенести
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              wrap(async () => {
                haptic("warn");
                await onDelete(task.id);
              })
            }
            className="rounded-md px-2 py-1 text-xs text-tg-destructive hover:bg-tg-secondary"
          >
            🗑 Удалить
          </button>
        </div>
      )}
      {moveOpen && !isDone && (
        <div className="mt-2 grid grid-cols-3 gap-1">
          {HORIZON_OPTIONS.map((h) => (
            <button
              key={h.slug}
              type="button"
              disabled={busy || h.slug === task.horizon_slug}
              onClick={() =>
                wrap(async () => {
                  haptic("select");
                  await onMove(task.id, h.slug);
                  setMoveOpen(false);
                })
              }
              className={
                "rounded-md px-2 py-1.5 text-xs " +
                (h.slug === task.horizon_slug
                  ? "bg-tg-button/20 text-tg-button"
                  : "bg-tg-secondary text-tg-text hover:bg-tg-secondary/80")
              }
            >
              {h.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
