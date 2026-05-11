import { useCallback, useEffect, useMemo, useState } from "react";
import {
  DndContext,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import { CalendarDays, Sparkles } from "lucide-react";
import { ApiError, apiClient } from "./api/client";
import { BottomNav, type NavTab } from "./components/BottomNav";
import { CategoryFilter } from "./components/CategoryFilter";
import { ComingSoon } from "./components/ComingSoon";
import { EmptyState } from "./components/EmptyState";
import { buildHeaderTitle, Header } from "./components/Header";
import { HorizonTabs } from "./components/HorizonTabs";
import { NoteDetail } from "./components/NoteDetail";
import { NotesList } from "./components/NotesList";
import { SettingsPage } from "./components/SettingsPage";
import { TaskCard } from "./components/TaskCard";
import { TaskDetail } from "./components/TaskDetail";
import { TrashPage } from "./components/TrashPage";
import { haptic } from "./lib/telegram";
import { navigate, navigateHome, useRoute } from "./lib/router";
import { StorageKeys, storageGet, storageSet } from "./lib/storage";
import type {
  Category,
  Horizon,
  HorizonSlug,
  Me,
  Task,
  TaskCounts,
} from "./types";

const EMPTY_COUNTS: TaskCounts = {
  today: 0,
  tomorrow: 0,
  week: 0,
  month: 0,
  year: 0,
  someday: 0,
  no_horizon: 0,
};

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
  const [counts, setCounts] = useState<TaskCounts>(EMPTY_COUNTS);
  const [activeHorizon, setActiveHorizon] = useState<string>(DEFAULT_HORIZON);
  const [selectedCategory, setSelectedCategory] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [authError, setAuthError] = useState<string | null>(null);
  const [prefsHydrated, setPrefsHydrated] = useState(false);
  const [showCategorySheet, setShowCategorySheet] = useState(false);
  // Phase 7c: Tasks + Settings tabs are real screens. Calendar still
  // renders a "coming soon" placeholder (Phase 5.5).
  const [activeTab, setActiveTab] = useState<NavTab>("tasks");

  const route = useRoute();
  const [notesRefresh, setNotesRefresh] = useState(0);
  const detailTaskId = useMemo(() => {
    if (route.path !== "/task/:id") return null;
    const raw = route.params.id;
    if (raw === undefined) return null;
    const parsed = Number.parseInt(raw, 10);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
  }, [route]);
  const noteRoute = useMemo<
    null | { kind: "create" } | { kind: "view"; noteId: number }
  >(() => {
    if (route.path === "/note/new") return { kind: "create" };
    if (route.path === "/note/:id") {
      const raw = route.params.id;
      if (raw === undefined) return null;
      const parsed = Number.parseInt(raw, 10);
      if (!Number.isFinite(parsed) || parsed <= 0) return null;
      return { kind: "view", noteId: parsed };
    }
    return null;
  }, [route]);

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

  // Phase 5.4: per-horizon badges. Single round-trip → counts for all
  // horizons. Refreshed on every mutation so badges stay live without
  // optimistic logic per-action (cheap query, predictable answer).
  const loadCounts = useCallback(async () => {
    try {
      const resp = await apiClient.taskCounts();
      setCounts(resp);
    } catch (err) {
      if (err instanceof ApiError && err.status !== 401 && err.status !== 404) {
        console.error("loadCounts failed", err);
      }
    }
  }, []);

  const refreshCategories = useCallback(async () => {
    try {
      const resp = await apiClient.categories();
      setCategories(resp);
    } catch (err) {
      if (err instanceof ApiError && err.status !== 401 && err.status !== 404) {
        console.error("loadCategories failed", err);
      }
    }
  }, []);

  useEffect(() => {
    loadShell().finally(() => setLoading(false));
  }, [loadShell]);

  // If the user lands on a note URL (deep link, refresh on /note/123),
  // make sure the Notes tab is the one we fall back to when they hit
  // «Назад» — otherwise close-detail jumps them to the Tasks list which
  // is jarring. We don't do this for task URLs because Tasks is the
  // default tab anyway.
  useEffect(() => {
    if (noteRoute !== null && activeTab !== "notes") {
      setActiveTab("notes");
    }
  }, [noteRoute, activeTab]);

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

  // Counts don't depend on the active horizon — fetch once when the
  // shell is ready and again after each successful mutation. Category
  // filter does NOT scope the badges (we want to show «3 tasks today»
  // regardless of which category is selected).
  useEffect(() => {
    if (!authError && prefsHydrated) {
      void loadCounts();
    }
  }, [authError, prefsHydrated, loadCounts]);

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
        void loadCounts();
        void refreshCategories();
      } catch (err) {
        // Revert optimistic update.
        loadTasks(activeHorizon, selectedCategory);
        console.error("done failed", err);
      }
    },
    [activeHorizon, selectedCategory, loadTasks, loadCounts, refreshCategories],
  );

  const handleMove = useCallback(
    async (id: number, slug: HorizonSlug) => {
      setTasks((prev) =>
        prev.map((t) => (t.id === id ? { ...t, horizon_slug: slug } : t)),
      );
      try {
        await apiClient.patchTask(id, { horizon_slug: slug });
        if (slug !== activeHorizon) {
          setTasks((prev) => prev.filter((t) => t.id !== id));
        }
        void loadCounts();
      } catch (err) {
        loadTasks(activeHorizon, selectedCategory);
        console.error("move failed", err);
      }
    },
    [activeHorizon, selectedCategory, loadTasks, loadCounts],
  );

  const handleOpenTask = useCallback((id: number) => {
    haptic("select");
    navigate(`/task/${id}`);
  }, []);

  const handleCloseDetail = useCallback(() => {
    navigateHome();
  }, []);

  const handleDetailMutated = useCallback(() => {
    void loadTasks(activeHorizon, selectedCategory);
    void loadCounts();
    void refreshCategories();
  }, [activeHorizon, selectedCategory, loadTasks, loadCounts, refreshCategories]);

  const handleOpenNote = useCallback((id: number) => {
    haptic("select");
    navigate(`/note/${id}`);
  }, []);

  const handleCreateNote = useCallback(() => {
    haptic("select");
    navigate("/note/new");
  }, []);

  const handleNoteMutated = useCallback(() => {
    setNotesRefresh((n) => n + 1);
  }, []);

  // Phase 5.4b: drag-n-drop. PointerSensor with delay activation so
  // a quick tap on a button inside the card still fires onClick;
  // long-press (250 ms) starts the drag. ``tolerance`` allows a few
  // pixels of jitter before activation cancels — important on touch
  // devices where the finger trembles slightly while pressing.
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { delay: 250, tolerance: 5 },
    }),
  );

  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      const { active, over } = event;
      if (over === null) return;
      const taskId = Number(active.id);
      const targetSlug = String(over.id);
      if (!Number.isFinite(taskId) || taskId <= 0) return;
      if (!VALID_HORIZONS.has(targetSlug as HorizonSlug)) return;
      const task = tasks.find((t) => t.id === taskId);
      if (task === undefined) return;
      if (task.horizon_slug === targetSlug) return; // no-op same horizon
      haptic("success");
      void handleMove(taskId, targetSlug as HorizonSlug);
    },
    [tasks, handleMove],
  );

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

  // Detail page is a full-bleed overlay. We render it inside the same
  // DndContext so any open sheets share haptic/keyboard handling
  // (though dragging is disabled inside the detail screen).
  if (detailTaskId !== null) {
    return (
      <DndContext sensors={sensors}>
        <TaskDetail
          taskId={detailTaskId}
          tz={tz}
          horizons={horizons}
          categories={categories}
          onClose={handleCloseDetail}
          onMutated={handleDetailMutated}
          onDeleted={handleCloseDetail}
        />
        <BottomNav active={activeTab} onChange={setActiveTab} />
      </DndContext>
    );
  }

  if (noteRoute !== null) {
    return (
      <DndContext sensors={sensors}>
        <NoteDetail
          mode={noteRoute}
          categories={categories}
          onClose={handleCloseDetail}
          onMutated={handleNoteMutated}
          onDeleted={handleCloseDetail}
        />
        <BottomNav
          active={activeTab}
          onChange={(tab) => {
            navigateHome();
            setActiveTab(tab);
          }}
        />
      </DndContext>
    );
  }

  if (route.path === "/trash") {
    return (
      <DndContext sensors={sensors}>
        <div
          className="mx-auto max-w-md px-4"
          style={{
            paddingTop: "calc(var(--safe-top) + 0.75rem)",
            paddingBottom: "calc(var(--safe-bottom) + 5.5rem)",
          }}
        >
          <TrashPage />
        </div>
        <BottomNav
          active={activeTab}
          onChange={(tab) => {
            navigateHome();
            setActiveTab(tab);
          }}
        />
      </DndContext>
    );
  }

  const titleSubtitle =
    activeTab === "tasks"
      ? me?.display_name
        ? `Привет, ${me.display_name}`
        : "Лента твоих задач"
      : activeTab === "notes"
        ? "Любой текст, который не задача"
        : undefined;

  const activeFilterLabel =
    selectedCategory === null
      ? undefined
      : categories.find((c) => c.id === selectedCategory)?.name;

  return (
    <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
      <div
        className="mx-auto max-w-md px-4"
        style={{
          paddingTop: "calc(var(--safe-top) + 0.75rem)",
          paddingBottom: "calc(var(--safe-bottom) + 5.5rem)",
        }}
      >
        <Header
          title={
            activeTab === "tasks"
              ? buildHeaderTitle(horizons, activeHorizon, counts)
              : activeTab === "notes"
                ? "Заметки"
                : activeTab === "settings"
                  ? "Настройки"
                  : "Календарь"
          }
          subtitle={titleSubtitle}
          showFilter={activeTab === "tasks"}
          selectedCategoryId={selectedCategory}
          filterLabel={activeFilterLabel}
          onOpenFilter={() => setShowCategorySheet(true)}
          onCreate={activeTab === "notes" ? handleCreateNote : undefined}
          createLabel={activeTab === "notes" ? "Новая заметка" : undefined}
        />
        {activeTab === "tasks" ? (
          <>
            <HorizonTabs
              horizons={horizons}
              active={activeHorizon}
              counts={counts}
              onChange={handleHorizonChange}
            />
            {tasks.length === 0 ? (
              <EmptyState
                icon={Sparkles}
                tone="emerald"
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
                      onOpen={handleOpenTask}
                    />
                  </li>
                ))}
              </ul>
            )}
          </>
        ) : activeTab === "notes" ? (
          <NotesList refreshSignal={notesRefresh} onOpen={handleOpenNote} />
        ) : activeTab === "calendar" ? (
          <ComingSoon
            icon={CalendarDays}
            tone="violet"
            title="Календарь скоро"
            description="Задачи с датами в сетке на месяц и неделю с drag-n-drop."
          />
        ) : me ? (
          <SettingsPage me={me} onUpdated={setMe} />
        ) : null}
      </div>
      <CategoryFilter
        open={showCategorySheet}
        onClose={() => setShowCategorySheet(false)}
        categories={categories}
        selectedId={selectedCategory}
        onChange={handleCategoryChange}
      />
      <BottomNav active={activeTab} onChange={setActiveTab} />
    </DndContext>
  );
}
