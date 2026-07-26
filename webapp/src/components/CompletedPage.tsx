// Phase 7e/C: "Выполненные" — a dedicated screen for completed tasks,
// separate from the Trash (deleted items). Done tasks are an
// achievement log: grouped by completion day, each can be returned to
// work ("вернуть в работу" → PATCH status=new, which also clears
// completed_at server-side).
//
// Self-contained like TrashPage: fetches its own data, mutates locally.

import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowLeft, CheckCircle2, RotateCcw } from "lucide-react";
import { apiClient } from "../api/client";
import { haptic } from "../lib/telegram";
import { navigateHome } from "../lib/router";
import { localDateKey } from "../lib/format";
import type { Task } from "../types";
import { IconTile } from "./IconTile";
import { SkeletonList } from "./Skeleton";

interface Props {
  tz: string;
  /** Called after a successful reopen so App.tsx can invalidate the
   *  list/board/calendar caches and reconcile the horizon badges. */
  onMutated?: () => void;
}

// Human day heading from a YYYY-MM-DD key, relative to today/yesterday.
function dayHeading(key: string, tz: string): string {
  const todayKey = localDateKey(new Date().toISOString(), tz);
  if (key === todayKey) return "Сегодня";
  const yKey = localDateKey(new Date(Date.now() - 86_400_000).toISOString(), tz);
  if (key === yKey) return "Вчера";
  const [y, m, d] = key.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d));
  return dt.toLocaleDateString("ru-RU", {
    day: "numeric",
    month: "long",
    timeZone: "UTC",
  });
}

export function CompletedPage({ tz, onMutated }: Props) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      const resp = await apiClient.tasks({
        status: "done",
        include_done: true,
        include_subtasks: true,
        limit: 200,
      });
      setTasks(resp);
    } catch {
      // keep stale list visible
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function reopen(task: Task) {
    setPending(task.id);
    try {
      await apiClient.patchTask(task.id, { status: "new" });
      haptic("success");
      setTasks((prev) => prev.filter((t) => t.id !== task.id));
      onMutated?.();
    } catch {
      haptic("error");
    } finally {
      setPending(null);
    }
  }

  // Group by completion day (fallback created_at for legacy done rows),
  // newest day first. The list already arrives sorted completed_at DESC.
  const groups = useMemo(() => {
    const map = new Map<string, Task[]>();
    for (const t of tasks) {
      const key = localDateKey(t.completed_at ?? t.created_at, tz) ?? "—";
      const arr = map.get(key);
      if (arr) arr.push(t);
      else map.set(key, [t]);
    }
    return [...map.entries()];
  }, [tasks, tz]);

  return (
    <div className="flex flex-col gap-5 pb-4">
      <div className="flex items-center gap-3 px-1">
        <button
          onClick={() => navigateHome()}
          className="ease-apple flex h-9 w-9 items-center justify-center rounded-xl text-tg-hint transition-all duration-200 active:scale-[0.92]"
        >
          <ArrowLeft size={20} strokeWidth={2.25} />
        </button>
        <h2 className="text-[17px] font-semibold text-tg-text">Выполненные</h2>
      </div>

      {loading && (
        <div className="px-4">
          <SkeletonList rows={4} kind="task" />
        </div>
      )}

      {!loading && tasks.length === 0 && (
        <div className="flex flex-col items-center gap-3 py-12 text-center">
          <IconTile icon={CheckCircle2} tone="emerald" size="lg" />
          <p className="text-[15px] text-tg-hint">Пока ничего не выполнено</p>
          <p className="max-w-[260px] text-[13px] text-tg-hint/70">
            Завершённые задачи собираются здесь — это история твоих
            достижений. Любую можно вернуть в работу.
          </p>
        </div>
      )}

      {groups.map(([key, items]) => (
        <section key={key}>
          <header className="mb-2 px-4 text-[13px] font-semibold tracking-tight text-tg-link">
            {dayHeading(key, tz)}
          </header>
          <div className="overflow-hidden rounded-3xl bg-bento-card shadow-bento ring-1 ring-black/5">
            <div className="divide-y divide-tg-divider/40">
              {items.map((task) => (
                <div
                  key={task.id}
                  className="flex min-h-[56px] items-center justify-between gap-3 px-4 py-3"
                >
                  <div className="flex min-w-0 flex-col gap-0.5">
                    <span className="truncate text-[15px] text-tg-hint line-through">
                      {task.title}
                    </span>
                    {task.category_name && (
                      <span className="truncate text-[12px] text-tg-hint/70">
                        {task.category_name}
                      </span>
                    )}
                  </div>
                  <button
                    disabled={pending === task.id}
                    onClick={() => reopen(task)}
                    className="ease-apple flex shrink-0 items-center gap-1.5 rounded-xl bg-bento px-3 py-2 text-[13px] font-medium text-tg-link ring-1 ring-black/[0.04] transition-all duration-200 active:scale-[0.96] disabled:opacity-40"
                  >
                    <RotateCcw size={15} strokeWidth={2.25} aria-hidden />
                    В работу
                  </button>
                </div>
              ))}
            </div>
          </div>
        </section>
      ))}
    </div>
  );
}
