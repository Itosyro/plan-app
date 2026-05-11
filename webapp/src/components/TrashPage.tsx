import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, RotateCcw, Trash2 } from "lucide-react";
import { apiClient } from "../api/client";
import { haptic } from "../lib/telegram";
import { navigateHome } from "../lib/router";
import type { TrashItem } from "../types";
import { IconTile } from "./IconTile";

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso + "Z").getTime();
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 1) return "только что";
  if (minutes < 60) return `${minutes} мин назад`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} ч назад`;
  return `${Math.floor(hours / 24)} д назад`;
}

export function TrashPage() {
  const [items, setItems] = useState<TrashItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const resp = await apiClient.trash();
      setItems(resp);
    } catch {
      // keep stale items visible
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function restore(item: TrashItem) {
    const key = `${item.kind}-${item.id}`;
    setPending(key);
    try {
      await apiClient.restoreTrashItem(item.kind, item.id);
      haptic("success");
      setItems((prev) => prev.filter((i) => !(i.kind === item.kind && i.id === item.id)));
    } catch {
      haptic("error");
    } finally {
      setPending(null);
    }
  }

  async function hardDelete(item: TrashItem) {
    const key = `${item.kind}-${item.id}`;
    setPending(key);
    try {
      await apiClient.hardDeleteTrashItem(item.kind, item.id);
      haptic("success");
      setItems((prev) => prev.filter((i) => !(i.kind === item.kind && i.id === item.id)));
    } catch {
      haptic("error");
    } finally {
      setPending(null);
    }
  }

  const tasks = items.filter((i) => i.kind === "task");
  const notes = items.filter((i) => i.kind === "note");

  return (
    <div className="flex flex-col gap-5 pb-4">
      <div className="flex items-center gap-3 px-1">
        <button
          onClick={() => navigateHome()}
          className="ease-apple flex h-9 w-9 items-center justify-center rounded-xl text-tg-hint transition-all duration-200 active:scale-[0.92]"
        >
          <ArrowLeft size={20} strokeWidth={2.25} />
        </button>
        <h2 className="text-[17px] font-semibold text-tg-text">Корзина</h2>
      </div>

      {loading && (
        <p className="px-4 text-sm text-tg-hint">Загрузка…</p>
      )}

      {!loading && items.length === 0 && (
        <div className="flex flex-col items-center gap-3 py-12 text-center">
          <IconTile icon={Trash2} tone="slate" size="lg" />
          <p className="text-[15px] text-tg-hint">Корзина пуста</p>
          <p className="max-w-[260px] text-[13px] text-tg-hint/70">
            Удалённые задачи и заметки хранятся здесь 24 часа
          </p>
        </div>
      )}

      {tasks.length > 0 && (
        <TrashSection title="Задачи" items={tasks} pending={pending} onRestore={restore} onDelete={hardDelete} />
      )}

      {notes.length > 0 && (
        <TrashSection title="Заметки" items={notes} pending={pending} onRestore={restore} onDelete={hardDelete} />
      )}
    </div>
  );
}

interface SectionProps {
  title: string;
  items: TrashItem[];
  pending: string | null;
  onRestore: (item: TrashItem) => void;
  onDelete: (item: TrashItem) => void;
}

function TrashSection({ title, items, pending, onRestore, onDelete }: SectionProps) {
  return (
    <section>
      <header className="mb-2 px-4 text-[11px] font-semibold uppercase tracking-[0.08em] text-tg-hint">
        {title}
      </header>
      <div className="flex flex-col gap-1.5">
        {items.map((item) => {
          const key = `${item.kind}-${item.id}`;
          const disabled = pending === key;
          return (
            <div
              key={key}
              className="ease-apple flex items-center justify-between rounded-2xl bg-bento-card px-4 py-3 shadow-bento ring-1 ring-black/[0.04] transition-all duration-200"
            >
              <div className="flex min-w-0 flex-col gap-0.5">
                <span className="truncate text-[15px] font-medium text-tg-text">
                  {item.title}
                </span>
                <span className="text-[12px] text-tg-hint">
                  {timeAgo(item.deleted_at)}
                  {item.category_name ? ` · ${item.category_name}` : ""}
                </span>
              </div>
              <div className="flex shrink-0 items-center gap-1">
                <button
                  disabled={disabled}
                  onClick={() => onRestore(item)}
                  className="ease-apple flex h-8 w-8 items-center justify-center rounded-xl text-tg-link transition-all duration-200 active:scale-[0.90] disabled:opacity-40"
                  title="Восстановить"
                >
                  <RotateCcw size={16} strokeWidth={2.25} />
                </button>
                <button
                  disabled={disabled}
                  onClick={() => onDelete(item)}
                  className="ease-apple flex h-8 w-8 items-center justify-center rounded-xl text-rose-500 transition-all duration-200 active:scale-[0.90] disabled:opacity-40"
                  title="Удалить навсегда"
                >
                  <Trash2 size={16} strokeWidth={2.25} />
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
