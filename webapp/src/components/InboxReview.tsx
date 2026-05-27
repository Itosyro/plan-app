// «Входящие» — review tab. Lists inbox entries the pipeline flagged
// (≥2 tasks or low confidence). The tasks already exist (вариант Б);
// here the user unchecks the wrong ones and taps «Подтвердить», which
// keeps the checked tasks and soft-deletes the rest. Cancel = just
// leave the card — it stays pending until confirmed.

import { useCallback, useEffect, useState } from "react";
import { Check, Inbox } from "lucide-react";
import { ApiError, apiClient } from "../api/client";
import { formatDue, priorityIcon } from "../lib/format";
import { haptic } from "../lib/telegram";
import type { InboxReview as Review } from "../types";
import { EmptyState } from "./EmptyState";

interface Props {
  tz: string;
  // Called after a successful confirm so the parent can refresh the
  // task list, counts, and the nav badge.
  onResolved: () => void;
}

export function InboxReview({ tz, onResolved }: Props) {
  const [reviews, setReviews] = useState<Review[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Per-entry set of task ids to keep. Seeded with every task checked.
  const [keep, setKeep] = useState<Record<number, Set<number>>>({});
  const [busy, setBusy] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      const resp = await apiClient.pendingInbox();
      const seed: Record<number, Set<number>> = {};
      for (const r of resp) seed[r.id] = new Set(r.tasks.map((t) => t.id));
      setKeep(seed);
      setReviews(resp);
      setError(null);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setError("Не удалось проверить вход.");
      } else {
        setError("Не удалось загрузить «Входящие».");
      }
      setReviews([]);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const toggle = (entryId: number, taskId: number) => {
    haptic("select");
    setKeep((prev) => {
      const set = new Set(prev[entryId] ?? []);
      if (set.has(taskId)) set.delete(taskId);
      else set.add(taskId);
      return { ...prev, [entryId]: set };
    });
  };

  const confirm = useCallback(
    async (review: Review) => {
      const keepIds = [...(keep[review.id] ?? new Set<number>())];
      setBusy(review.id);
      // Optimistically drop the card — it's resolved either way.
      setReviews((prev) => (prev ? prev.filter((r) => r.id !== review.id) : prev));
      try {
        await apiClient.confirmInbox(review.id, keepIds);
        haptic("success");
        onResolved();
      } catch (err) {
        haptic("error");
        console.error("confirm inbox failed", err);
        await load(); // re-fetch to restore the card we optimistically removed
      } finally {
        setBusy(null);
      }
    },
    [keep, onResolved, load],
  );

  if (reviews === null) {
    return <div className="py-10 text-center text-sm text-tg-hint">Загружаем…</div>;
  }

  if (error !== null && reviews.length === 0) {
    return <EmptyState icon={Inbox} tone="amber" title="Не получилось" hint={error} />;
  }

  if (reviews.length === 0) {
    return (
      <EmptyState
        icon={Inbox}
        tone="emerald"
        title="Всё разобрано"
        hint="Сюда падают задачи на проверку, когда из сообщения вышло несколько штук или бот не уверен в распознавании. Сейчас проверять нечего."
      />
    );
  }

  return (
    <ul className="flex flex-col gap-3">
      {reviews.map((review) => {
        const keepSet = keep[review.id] ?? new Set<number>();
        return (
          <li
            key={review.id}
            className="rounded-3xl bg-bento-card p-4 shadow-bento ring-1 ring-black/5"
          >
            {review.text && (
              <p className="mb-3 border-l-2 border-tg-button/30 pl-3 text-[13px] italic leading-snug text-tg-hint">
                «{review.text}»
              </p>
            )}
            <ul className="flex flex-col gap-1.5">
              {review.tasks.map((task) => {
                const checked = keepSet.has(task.id);
                const due = formatDue(task.due_at, tz);
                return (
                  <li key={task.id}>
                    <button
                      type="button"
                      aria-pressed={checked}
                      onClick={() => toggle(review.id, task.id)}
                      className={
                        "ease-apple flex w-full items-start gap-2.5 rounded-2xl px-3 py-2 text-left transition-all duration-150 active:scale-[0.99] " +
                        (checked ? "bg-bento" : "bg-bento/40 opacity-60")
                      }
                    >
                      <span
                        className={
                          "mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md ring-1 transition-colors " +
                          (checked
                            ? "bg-tg-button text-white ring-tg-button"
                            : "bg-transparent text-transparent ring-tg-hint/50")
                        }
                      >
                        <Check size={13} strokeWidth={3} aria-hidden />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span
                          className={
                            "block text-[14px] leading-snug " +
                            (checked ? "text-tg-text" : "text-tg-hint line-through")
                          }
                        >
                          {priorityIcon(task.priority)} {task.title}
                        </span>
                        {(task.category_name || due) && (
                          <span className="mt-0.5 block text-[12px] text-tg-hint">
                            {task.category_name}
                            {task.category_name && due ? " · " : ""}
                            {due}
                          </span>
                        )}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
            <div className="mt-3 flex items-center justify-between gap-3">
              <span className="text-[12px] text-tg-hint">
                Оставлю {keepSet.size} из {review.tasks.length}
              </span>
              <button
                type="button"
                disabled={busy === review.id}
                onClick={() => void confirm(review)}
                className="ease-apple rounded-2xl bg-tg-button px-4 py-2 text-[14px] font-semibold text-white shadow-bento transition-all duration-150 active:scale-95 disabled:opacity-60"
              >
                Подтвердить
              </button>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
