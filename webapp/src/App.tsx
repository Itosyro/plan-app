import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, apiClient } from "./api/client";
import { CategoryFilter } from "./components/CategoryFilter";
import { EmptyState } from "./components/EmptyState";
import { Header } from "./components/Header";
import { HorizonTabs } from "./components/HorizonTabs";
import { TaskCard } from "./components/TaskCard";
import { StorageKeys, storageGet, storageSet } from "./lib/storage";
import type { Category, Horizon, HorizonSlug, Me, Task } from "./types";

const DEFAULT_HORIZON: HorizonSlug = "today";
const VALID_HORIZONS: ReadonlySet<HorizonSlug> = new Set([
  "today",
  "tomorrow",
  "week",
  "month",
  "year",
  "someday",
]);

export default function App() {
  const [me, setMe] = useState<Me | null>(null);
  const [horizons, setHorizons] = useState<Horizon[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [activeHorizon, setActiveHorizon] = useState<string>(DEFAULT_HORIZON);
  const [selectedCategory, setSelectedCategory] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [authError, setAuthError] = useState<string | null>(null);
  const [prefsHydrated, setPrefsHydrated] = useState(false);

  const loadShell = useCallback(async () => {
    try {
      const [meResp, horizonsResp, categoriesResp] = await Promise.all([
        apiClient.me(),
        apiClient.horizons(),
        apiClient.categories(),
      ]);
      setMe(meResp);
      setHorizons(horizonsResp);
      setCategories(categoriesResp);
      setAuthError(null);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 401) {
          setAuthError(
            "Не удалось проверить вход. Открой бот через @daylirobot и нажми «Открыть план» в меню.",
          );
        } else if (err.status === 404) {
          setAuthError("Сначала пройди /start в боте — мы ещё не знакомы.");
        } else {
          setAuthError("Ошибка соединения. Попробуй позже.");
        }
      } else {
        setAuthError("Ошибка соединения. Попробуй позже.");
      }
    }
  }, []);

  const loadTasks = useCallback(
    async (horizon: string, categoryId: number | null) => {
      try {
        const resp = await apiClient.tasks({
          horizon,
          category_id: categoryId ?? undefined,
        });
        setTasks(resp);
      } catch (err) {
        if (err instanceof ApiError && err.status !== 401 && err.status !== 404) {
          console.error("loadTasks failed", err);
        }
      }
    },
    [],
  );

  useEffect(() => {
    loadShell().finally(() => setLoading(false));
  }, [loadShell]);

  // Hydrate UI prefs from Telegram CloudStorage (or localStorage fallback).
  // This runs in parallel with the API shell load so first paint isn't
  // blocked. The first task fetch is gated on ``prefsHydrated`` so we
  // don't load tasks twice (once for the default horizon, again for the
  // restored one).
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const [storedHorizon, storedCategory] = await Promise.all([
        storageGet(StorageKeys.lastHorizon),
        storageGet(StorageKeys.lastCategory),
      ]);
      if (cancelled) return;
      if (storedHorizon && VALID_HORIZONS.has(storedHorizon as HorizonSlug)) {
        setActiveHorizon(storedHorizon);
      }
      if (storedCategory) {
        const parsed = Number.parseInt(storedCategory, 10);
        if (Number.isFinite(parsed) && parsed > 0) {
          setSelectedCategory(parsed);
        }
      }
      setPrefsHydrated(true);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!authError && prefsHydrated) {
      loadTasks(activeHorizon, selectedCategory);
    }
  }, [activeHorizon, selectedCategory, authError, prefsHydrated, loadTasks]);

  // Persist horizon choice. We don't persist on every render — the
  // setActiveHorizon path is the only way it changes.
  const handleHorizonChange = useCallback((slug: string) => {
    setActiveHorizon(slug);
    void storageSet(StorageKeys.lastHorizon, slug);
  }, []);

  const handleCategoryChange = useCallback((categoryId: number | null) => {
    setSelectedCategory(categoryId);
    void storageSet(
      StorageKeys.lastCategory,
      categoryId === null ? "" : String(categoryId),
    );
  }, []);

  const handleDone = useCallback(
    async (id: number) => {
      setTasks((prev) =>
        prev.map((t) => (t.id === id ? { ...t, status: "done" } : t)),
      );
      try {
        await apiClient.patchTask(id, { status: "done" });
        // Drop completed tasks from the visible list a moment later so
        // the user has time to register the strikethrough animation.
        setTimeout(() => {
          setTasks((prev) => prev.filter((t) => t.id !== id));
        }, 350);
      } catch (err) {
        // Revert optimistic update.
        loadTasks(activeHorizon, selectedCategory);
        console.error("done failed", err);
      }
    },
    [activeHorizon, selectedCategory, loadTasks],
  );

  const handleMove = useCallback(
    async (id: number, slug: HorizonSlug) => {
      setTasks((prev) =>
        prev.map((t) => (t.id === id ? { ...t, horizon_slug: slug } : t)),
      );
      try {
        await apiClient.patchTask(id, { horizon_slug: slug });
        // Removed from current horizon if user moved away.
        if (slug !== activeHorizon) {
          setTasks((prev) => prev.filter((t) => t.id !== id));
        }
      } catch (err) {
        loadTasks(activeHorizon, selectedCategory);
        console.error("move failed", err);
      }
    },
    [activeHorizon, selectedCategory, loadTasks],
  );

  const handleDelete = useCallback(
    async (id: number) => {
      setTasks((prev) => prev.filter((t) => t.id !== id));
      try {
        await apiClient.deleteTask(id);
      } catch (err) {
        loadTasks(activeHorizon, selectedCategory);
        console.error("delete failed", err);
      }
    },
    [activeHorizon, selectedCategory, loadTasks],
  );

  const counts = useMemo(() => {
    // Quick hint counts shown next to horizon tabs. We only populate the
    // active horizon's count from the loaded tasks; other counts come
    // back as 0 until that tab is opened. A future PR can switch to a
    // single ``GET /api/tasks/counts`` endpoint.
    return { [activeHorizon]: tasks.length };
  }, [activeHorizon, tasks.length]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-tg-hint">
        Загружаем…
      </div>
    );
  }

  if (authError) {
    return (
      <div className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center px-6 text-center">
        <div className="text-5xl">🔒</div>
        <h2 className="mt-3 text-lg font-medium text-tg-text">Нужен вход</h2>
        <p className="mt-2 text-sm text-tg-hint">{authError}</p>
      </div>
    );
  }

  const tz = me?.tz ?? "Europe/Moscow";

  return (
    <div
      className="mx-auto max-w-md px-4"
      style={{
        paddingTop: "calc(var(--safe-top) + 0.75rem)",
        paddingBottom: "calc(var(--safe-bottom) + 1rem)",
      }}
    >
      <Header me={me} />
      <HorizonTabs
        horizons={horizons}
        active={activeHorizon}
        counts={counts}
        onChange={handleHorizonChange}
      />
      <CategoryFilter
        categories={categories}
        selectedId={selectedCategory}
        onChange={handleCategoryChange}
      />
      {tasks.length === 0 ? (
        <EmptyState
          emoji="🎉"
          title="Ничего на горизонте"
          hint="Скинь голос или текст в бот — задачи появятся здесь автоматически."
        />
      ) : (
        <ul className="flex flex-col gap-2">
          {tasks.map((task) => (
            <li key={task.id}>
              <TaskCard
                task={task}
                tz={tz}
                onDone={handleDone}
                onMove={handleMove}
                onDelete={handleDelete}
              />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
