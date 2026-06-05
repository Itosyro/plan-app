import { useState } from "react";
import { useDraggable } from "@dnd-kit/core";
import { Check, Clock, Flag, ListChecks, Tag } from "lucide-react";
import type { Task } from "../types";
import { formatDue } from "../lib/format";
import { haptic } from "../lib/telegram";
import { IconTile, type TileTone } from "./IconTile";

// Only ``high`` and ``low`` show a priority chip; ``medium`` is the
// default tone and would just be visual noise on every card. Tones
// chosen to match the Mira reference: warm red for urgent, calm
// green for low-priority.
const PRIORITY_TONE: Record<"high" | "low", TileTone> = {
  high: "rose",
  low: "emerald",
};

interface Props {
  task: Task;
  tz: string;
  onDone: (id: number) => Promise<void> | void;
  onOpen: (id: number) => void;
  // Phase 7e/C: tapping a lingering done card's checkbox returns it to
  // work. When omitted, a done checkbox stays inert (legacy surfaces).
  onReopen?: (id: number) => Promise<void> | void;
}

export function TaskCard({ task, tz, onDone, onOpen, onReopen }: Props) {
  const [busy, setBusy] = useState(false);
  const due = formatDue(task.due_at, tz);
  const isDone = task.status === "done";
  const priorityTone =
    task.priority === "high" || task.priority === "low"
      ? PRIORITY_TONE[task.priority]
      : null;

  // Phase 5.4b: drag-n-drop. The whole card is draggable; activation
  // is delayed (PointerSensor in App.tsx) so a quick tap on the
  // checkbox or card body still fires onClick. Long-press → card
  // lifts → user drags up to a horizon pill which is registered as
  // a drop target in HorizonTabs.
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: task.id,
    disabled: isDone,
  });

  const dragStyle = transform
    ? {
        transform: `translate3d(${transform.x}px, ${transform.y}px, 0) scale(1.02)`,
        zIndex: 50,
      }
    : undefined;

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
      ref={setNodeRef}
      style={dragStyle}
      {...attributes}
      {...listeners}
      className={
        "ease-apple touch-manipulation rounded-3xl bg-bento-card p-4 ring-1 ring-black/5 transition-all duration-200 " +
        (isDone ? "opacity-50 " : "opacity-100 ") +
        (isDragging ? "shadow-bento-lg" : "shadow-bento")
      }
    >
      <div className="flex items-start gap-3">
        <button
          type="button"
          aria-label={isDone ? "Вернуть в работу" : "Отметить выполненной"}
          disabled={busy || (isDone && !onReopen)}
          onClick={(e) => {
            e.stopPropagation();
            void wrap(async () => {
              if (isDone) {
                if (onReopen) {
                  haptic("select");
                  await onReopen(task.id);
                }
                return;
              }
              haptic("success");
              await onDone(task.id);
            });
          }}
          className={
            "ease-spring mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border-[1.5px] transition-all duration-300 " +
            (isDone
              ? "scale-100 border-emerald-500 bg-emerald-500 text-white"
              : "scale-100 border-tg-hint/40 bg-bento-card hover:border-emerald-400 active:scale-90")
          }
        >
          {isDone && <Check size={14} strokeWidth={3} />}
        </button>
        <button
          type="button"
          aria-label={`Открыть «${task.title}»`}
          onClick={(e) => {
            e.stopPropagation();
            if (isDone) return;
            haptic("select");
            onOpen(task.id);
          }}
          disabled={isDone}
          className="ease-apple -m-1 min-w-0 flex-1 rounded-2xl p-1 text-left transition-all duration-150 active:scale-[0.995]"
        >
          <div className="flex items-start gap-2">
            {priorityTone && (
              <IconTile
                icon={Flag}
                tone={priorityTone}
                size="sm"
                label={
                  task.priority === "high"
                    ? "Высокий приоритет"
                    : "Низкий приоритет"
                }
              />
            )}
            <div className="min-w-0">
              <div
                className={
                  "font-display flex min-w-0 items-start gap-1.5 break-words pt-0.5 text-[16px] font-medium leading-snug tracking-tight " +
                  (isDone ? "text-tg-hint line-through" : "text-tg-text")
                }
              >
                {task.title_original && (
                  <span
                    aria-label="Первый шаг"
                    title="Первый шаг — конкретное действие, с которого можно начать"
                    className="shrink-0 select-none pt-px text-[14px] leading-none"
                  >
                    🎯
                  </span>
                )}
                <span className="min-w-0 break-words">{task.title}</span>
              </div>
              {task.title_original && !isDone && (
                <div
                  className="mt-0.5 break-words text-[12px] italic leading-snug text-tg-hint"
                  title="Оригинальная формулировка"
                >
                  {task.title_original}
                </div>
              )}
            </div>
          </div>
          {(due || task.category_name || task.subtasks_total > 0) && (
            <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-tg-hint">
              {due && (
                <span className="inline-flex items-center gap-1 rounded-full bg-bento px-2 py-0.5">
                  <Clock size={12} strokeWidth={2} aria-hidden />
                  {due}
                </span>
              )}
              {task.subtasks_total > 0 && (
                <span
                  className={
                    "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] " +
                    (task.subtasks_done === task.subtasks_total
                      ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                      : "bg-bento text-tg-text/70")
                  }
                  aria-label={`${task.subtasks_done} из ${task.subtasks_total} подзадач выполнено`}
                >
                  <ListChecks size={11} strokeWidth={2} aria-hidden />
                  {task.subtasks_done}/{task.subtasks_total}
                </span>
              )}
              {task.category_name && (
                <span className="inline-flex items-center gap-1 rounded-full bg-bento px-2 py-0.5 text-[11px] text-tg-text/70">
                  <Tag size={11} strokeWidth={2} aria-hidden />
                  {task.category_name}
                </span>
              )}
            </div>
          )}
        </button>
      </div>
    </div>
  );
}
