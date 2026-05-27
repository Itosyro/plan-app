// «Входящие» — review tab. Lists inbox entries the pipeline flagged
// (≥2 tasks or low confidence). The tasks already exist (вариант Б);
// here the user unchecks the wrong ones and taps «Подтвердить», which
// keeps the checked tasks and soft-deletes the rest. Cancel = just
// leave the card — it stays pending until confirmed.

import { useCallback, useEffect, useState } from "react";
import { Check, Inbox, Pencil } from "lucide-react";
import { ApiError, apiClient } from "../api/client";
import { formatDue, priorityIcon } from "../lib/format";
import { haptic } from "../lib/telegram";
import type { InboxReview as Review, Task } from "../types";
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
  // Inline title edit: which task id is open for editing, its draft text,
  // the id with a save in flight, and a save error to surface.
  const [editing, setEditing] = useState<number | null>(null);
  const [titleDraft, setTitleDraft] = useState("");
  const [savingTitle, setSavingTitle] = useState<number | null>(null);
  const [titleError, setTitleError] = useState<string | null>(null);

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

  const startEdit = (task: Task) => {
    haptic("select");
    setTitleError(null);
    setTitleDraft(task.title);
    setEditing(task.id);
  };

  // Commit the title draft on blur. Skips the API when empty (revert) or
  // unchanged; on success patches local state so the card updates instantly.
  const saveTitle = useCallback(
    async (task: Task) => {
      const trimmed = titleDraft.trim();
      setEditing(null);
      if (!trimmed || trimmed === task.title) return; // revert / no-op
      setSavingTitle(task.id);
      setTitleError(null);
      try {
        const fresh = await apiClient.patchTask(task.id, { title: trimmed });
        haptic("success");
        setReviews((prev) =>
          prev
            ? prev.map((r) => ({
                ...r,
                tasks: r.tasks.map((t) =>
                  t.id === task.id ? { ...t, title: fresh.title } : t,
                ),
              }))
            : prev,
        );
      } catch (err) {
        haptic("error");
        console.error("patch inbox task title failed", err);
        setTitleError(
          err instanceof ApiError && err.status === 422
            ? "Не получилось — проверь название."
            : "Не удалось сохранить название.",
        );
      } finally {
        setSavingTitle(null);
      }
    },
    [titleDraft],
  );

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
      {titleError && (
        <li className="rounded-2xl bg-rose-50 px-4 py-3 text-[13px] text-rose-700 ring-1 ring-rose-100 dark:bg-rose-950/40 dark:text-rose-200">
          {titleError}
        </li>
      )}
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
                const isEditing = editing === task.id;
                const isSaving = savingTitle === task.id;
                return (
                  <li key={task.id}>
                    <div
                      className={
                        "ease-apple flex w-full items-start gap-2.5 rounded-2xl px-3 py-2 transition-all duration-150 " +
                        (checked ? "bg-bento" : "bg-bento/40 opacity-60")
                      }
                    >
                      <button
                        type="button"
                        aria-pressed={checked}
                        aria-label={checked ? "Не оставлять" : "Оставить"}
                        onClick={() => toggle(review.id, task.id)}
                        className={
                          "ease-apple mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md ring-1 transition-all duration-150 active:scale-90 " +
                          (checked
                            ? "bg-tg-button text-white ring-tg-button"
                            : "bg-transparent text-transparent ring-tg-hint/50")
                        }
                      >
                        <Check size={13} strokeWidth={3} aria-hidden />
                      </button>
                      <div className="min-w-0 flex-1">
                        {isEditing ? (
                          <textarea
                            autoFocus
                            value={titleDraft}
                            maxLength={256}
                            rows={2}
                            disabled={isSaving}
                            onChange={(e) => setTitleDraft(e.target.value)}
                            onBlur={() => void saveTitle(task)}
                            className="w-full resize-none rounded-xl bg-bento-card px-2 py-1 text-[14px] leading-snug text-tg-text ring-1 ring-tg-button/40 focus:outline-none focus:ring-tg-button"
                            placeholder="Что нужно сделать?"
                          />
                        ) : (
                          <button
                            type="button"
                            aria-pressed={checked}
                            onClick={() => toggle(review.id, task.id)}
                            className="block w-full text-left"
                          >
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
                          </button>
                        )}
                      </div>
                      {!isEditing && (
                        <button
                          type="button"
                          disabled={isSaving}
                          aria-label="Исправить название"
                          onClick={() => startEdit(task)}
                          className="ease-apple mt-0.5 inline-flex shrink-0 items-center gap-1 rounded-lg px-1.5 py-0.5 text-[12px] text-tg-hint transition-all duration-150 active:scale-95 hover:text-tg-text disabled:opacity-50"
                        >
                          <Pencil size={12} strokeWidth={2.25} aria-hidden />
                          Исправить
                        </button>
                      )}
                    </div>
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
