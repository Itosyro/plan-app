import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from "react";
import {
  closestCorners,
  DndContext,
  DragOverlay,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import { Sparkles } from "lucide-react";
import { ApiError, apiClient } from "./api/client";
import { BottomNav, type NavTab } from "./components/BottomNav";
import { CalendarView, CAL_CACHE_PREFIX, CALDAY_PREFIX } from "./components/CalendarView";
import { CategoryFilter } from "./components/CategoryFilter";
import {
  KanbanView,
  KanbanCardView,
  KCAT_PREFIX,
  KCAT_NONE,
} from "./components/KanbanView";
import { EmptyState } from "./components/EmptyState";
import { buildHeaderTitle, Header } from "./components/Header";
import { HorizonTabs } from "./components/HorizonTabs";
import { NotesList, NOTES_CACHE_KEY } from "./components/NotesList";
import { LayoutSheet } from "./components/LayoutSheet";
import { SkeletonAppShell } from "./components/Skeleton";
import { TaskCard } from "./components/TaskCard";
import { invalidate, mutateCache } from "./lib/cache";
import { localDateKey } from "./lib/format";

// Screens that aren't part of the first paint (the Tasks tab) are
// code-split so the initial bundle stays small and the Mini-App opens
// fast. They're prefetched on idle right after mount (see effect below),
// so by the time the user taps another tab the chunk is already warm and
// the Suspense fallback never actually shows.
const importTaskDetail = () => import("./components/TaskDetail");
const importNoteDetail = () => import("./components/NoteDetail");
const importSettingsPage = () => import("./components/SettingsPage");
const importInboxReview = () => import("./components/InboxReview");
const importTrashPage = () => import("./components/TrashPage");
const importCompletedPage = () => import("./components/CompletedPage");
const importSearchOverlay = () => import("./components/SearchOverlay");

const TaskDetail = lazy(() =>
  importTaskDetail().then((m) => ({ default: m.TaskDetail })),
);
const NoteDetail = lazy(() =>
  importNoteDetail().then((m) => ({ default: m.NoteDetail })),
);
const SettingsPage = lazy(() =>
  importSettingsPage().then((m) => ({ default: m.SettingsPage })),
);
const InboxReview = lazy(() =>
  importInboxReview().then((m) => ({ default: m.InboxReview })),
);
const TrashPage = lazy(() =>
  importTrashPage().then((m) => ({ default: m.TrashPage })),
);
const CompletedPage = lazy(() =>
  importCompletedPage().then((m) => ({ default: m.CompletedPage })),
);
const SearchOverlay = lazy(() =>
  importSearchOverlay().then((m) => ({ default: m.SearchOverlay })),
);

function ScreenFallback() {
  return (
    <div className="py-16 text-center text-sm text-tg-hint">Загружаем…</div>
  );
}
import {
  DEFAULT_LAYOUT_PREFS,
  applyFilters,
  applySort,
  groupTasks,
  parseLayoutPrefs,
  serializeLayoutPrefs,
  type LayoutPrefs,
} from "./lib/layoutPrefs";
import { haptic } from "./lib/telegram";
import { navigate, navigateHome, useRoute } from "./lib/router";
import { StorageKeys, storageGet, storageSet } from "./lib/storage";
import type {
  Category,
  Horizon,
  HorizonSlug,
  Me,
  Note,
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
  const [boardRefresh, setBoardRefresh] = useState(0);
  // Optimistic drag payloads: dispatched the instant a drop resolves so
  // the board/calendar move the card in place (no full refetch flash).
  // The bumped ``nonce`` is what the child effect keys on.
  const [boardOptimistic, setBoardOptimistic] = useState<{
    id: number;
    categoryId: number | null;
    nonce: number;
  } | null>(null);
  // «Входящие» pending-review count for the nav badge.
  const [inboxCount, setInboxCount] = useState(0);
  const [tasksView, setTasksView] = useState<"list" | "board">("list");
  const [showLayoutSheet, setShowLayoutSheet] = useState(false);
  const [showSearch, setShowSearch] = useState(false);
  // Phase 7e/F1: «Раскладка» toggle — show/hide done tasks in the list.
  const [showCompleted, setShowCompleted] = useState(true);
  // Phase 7e/F2: «Раскладка» list grouping / sorting / filtering. One blob
  // hydrated from + persisted to CloudStorage under StorageKeys.layoutPrefs.
  const [layoutPrefs, setLayoutPrefs] = useState<LayoutPrefs>(
    DEFAULT_LAYOUT_PREFS,
  );
  // Snapshot of the card being dragged on the kanban board, rendered in
  // the DragOverlay portal (#7e/A fix).
  const [activeDragTask, setActiveDragTask] = useState<Task | null>(null);
  const tz = me?.tz ?? "Europe/Moscow";
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
          // Phase 7e/C: pull recently-done tasks too so they can linger
          // struck-through in the list; the render filter hides ones
          // completed > 24h ago (they live in the «Выполненные» screen).
          include_done: true,
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

  // «Входящие» badge count. Cheap — the pending list is small. Refreshed
  // on shell load and after a review is confirmed.
  const loadInboxCount = useCallback(async () => {
    try {
      const resp = await apiClient.pendingInbox();
      setInboxCount(resp.length);
    } catch (err) {
      if (err instanceof ApiError && err.status !== 401 && err.status !== 404) {
        console.error("loadInboxCount failed", err);
      }
    }
  }, []);

  useEffect(() => {
    loadShell().finally(() => setLoading(false));
  }, [loadShell]);

  // Warm the code-split screens on idle, right after first paint, so the
  // first tap on another tab/detail page doesn't wait on a chunk fetch.
  useEffect(() => {
    const prefetch = () => {
      void importTaskDetail();
      void importNoteDetail();
      void importSettingsPage();
      void importInboxReview();
      void importTrashPage();
      void importCompletedPage();
      void importSearchOverlay();
    };
    const ric = window.requestIdleCallback;
    if (ric) {
      const id = ric(prefetch);
      return () => window.cancelIdleCallback?.(id);
    }
    const t = window.setTimeout(prefetch, 1200);
    return () => window.clearTimeout(t);
  }, []);

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
      const [
        storedHorizon,
        storedCategory,
        storedView,
        storedShowDone,
        storedLayoutPrefs,
      ] = await Promise.all([
        storageGet(StorageKeys.lastHorizon),
        storageGet(StorageKeys.lastCategory),
        storageGet(StorageKeys.lastTasksView),
        storageGet(StorageKeys.showCompleted),
        storageGet(StorageKeys.layoutPrefs),
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
      if (storedView === "board" || storedView === "list") {
        setTasksView(storedView);
      }
      if (storedShowDone === "0") setShowCompleted(false);
      setLayoutPrefs(parseLayoutPrefs(storedLayoutPrefs));
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

  useEffect(() => {
    if (!authError && prefsHydrated) {
      void loadInboxCount();
    }
  }, [authError, prefsHydrated, loadInboxCount]);

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

  // Phase 7e/F2: merge a partial layout-prefs patch into state and persist
  // the whole blob (single CloudStorage key, well under the 4096 cap).
  const updateLayoutPrefs = useCallback((patch: Partial<LayoutPrefs>) => {
    setLayoutPrefs((prev) => {
      const next = { ...prev, ...patch };
      void storageSet(StorageKeys.layoutPrefs, serializeLayoutPrefs(next));
      return next;
    });
  }, []);

  const handleResetLayoutPrefs = useCallback(() => {
    setLayoutPrefs(DEFAULT_LAYOUT_PREFS);
    void storageSet(
      StorageKeys.layoutPrefs,
      serializeLayoutPrefs(DEFAULT_LAYOUT_PREFS),
    );
  }, []);

  const handleDone = useCallback(
    async (id: number) => {
      // Phase 7e/C linger: the task stays in the list, struck-through,
      // with a fresh completed_at — the render filter keeps it visible
      // for 24h. No more 350ms removal; re-tap (handleReopen) undoes it.
      const nowIso = new Date().toISOString();
      setTasks((prev) =>
        prev.map((t) =>
          t.id === id ? { ...t, status: "done", completed_at: nowIso } : t,
        ),
      );
      try {
        await apiClient.patchTask(id, { status: "done" });
        void loadCounts();
        void refreshCategories();
        invalidate(CAL_CACHE_PREFIX, { prefix: true });
        setBoardRefresh((n) => n + 1);
      } catch (err) {
        loadTasks(activeHorizon, selectedCategory);
        console.error("done failed", err);
      }
    },
    [activeHorizon, selectedCategory, loadTasks, loadCounts, refreshCategories],
  );

  const handleReopen = useCallback(
    async (id: number) => {
      setTasks((prev) =>
        prev.map((t) =>
          t.id === id ? { ...t, status: "new", completed_at: null } : t,
        ),
      );
      try {
        await apiClient.patchTask(id, { status: "new" });
        void loadCounts();
        void refreshCategories();
        invalidate(CAL_CACHE_PREFIX, { prefix: true });
        setBoardRefresh((n) => n + 1);
      } catch (err) {
        loadTasks(activeHorizon, selectedCategory);
        console.error("reopen failed", err);
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
        setBoardRefresh((n) => n + 1);
      } catch (err) {
        loadTasks(activeHorizon, selectedCategory);
        setBoardRefresh((n) => n + 1);
        console.error("move failed", err);
      }
    },
    [activeHorizon, selectedCategory, loadTasks, loadCounts],
  );

  // Kanban drop: re-assign the task's category (null = "Без категории"
  // column). Move the card in place optimistically, then patch. Only on
  // failure do we bump ``boardRefresh`` to refetch and revert.
  const handleSetCategory = useCallback(
    async (id: number, categoryId: number | null) => {
      setBoardOptimistic({ id, categoryId, nonce: Date.now() });
      try {
        await apiClient.patchTask(id, { category_id: categoryId });
        void loadCounts();
        void refreshCategories();
      } catch (err) {
        setBoardRefresh((n) => n + 1);
        console.error("set category failed", err);
      }
    },
    [loadCounts, refreshCategories],
  );

  // "+ Раздел" on the board creates a category = new column.
  const handleCreateCategoryColumn = useCallback(
    async (name: string) => {
      await apiClient.createCategory(name);
      await refreshCategories();
    },
    [refreshCategories],
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
    invalidate(CAL_CACHE_PREFIX, { prefix: true });
  }, [activeHorizon, selectedCategory, loadTasks, loadCounts, refreshCategories]);

  // Optimistic delete from the detail screen: drop the row from the list
  // instantly so closing the detail reveals it already gone. The detail's
  // background DELETE then calls ``handleDetailMutated`` to reconcile.
  const handleTaskOptimisticDelete = useCallback((id: number) => {
    setTasks((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const handleOpenNote = useCallback((id: number) => {
    haptic("select");
    navigate(`/note/${id}`);
  }, []);

  const handleCreateNote = useCallback(() => {
    haptic("select");
    navigate("/note/new");
  }, []);

  const handleNoteMutated = useCallback(() => {
    // Background server truth: invalidate the cached list so any
    // mounted NotesList refetches. Optimistic write was already
    // applied via ``handleNoteOptimisticDelete`` (no flicker).
    invalidate(NOTES_CACHE_KEY);
  }, []);

  const handleNoteOptimisticDelete = useCallback((id: number) => {
    // Drop the note from the cached list the instant the detail
    // confirms — NotesList repaints from the new cache without
    // needing a prop or its own optimistic-delete state.
    mutateCache<Note[]>(NOTES_CACHE_KEY, (prev) =>
      prev ? prev.filter((n) => n.id !== id) : [],
    );
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

  const handleReschedule = useCallback(
    async (id: number, dueAtIso: string) => {
      // Shift the event onto the target day in place across every
      // cached calendar window; refetch only on failure to revert.
      mutateCache<Task[]>(
        CAL_CACHE_PREFIX,
        (prev) =>
          (prev ?? []).map((t) =>
            t.id === id ? { ...t, due_at: dueAtIso } : t,
          ),
        { prefix: true },
      );
      try {
        await apiClient.patchTask(id, { due_at: dueAtIso });
        void loadCounts();
      } catch (err) {
        console.error("reschedule failed", err);
        invalidate(CAL_CACHE_PREFIX, { prefix: true });
      }
    },
    [loadCounts],
  );

  const handleDragStart = useCallback((event: DragStartEvent) => {
    const data = event.active.data.current as { task?: Task } | undefined;
    setActiveDragTask(data?.task ?? null);
  }, []);

  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      const { active, over } = event;
      setActiveDragTask(null);
      if (over === null) return;
      const taskId = Number(active.id);
      if (!Number.isFinite(taskId) || taskId <= 0) return;
      const overId = String(over.id);

      // Kanban column drop (Phase 7e/A): re-assign category. The drag
      // payload carries the card's current category to skip no-op drops.
      if (overId.startsWith(KCAT_PREFIX)) {
        const targetCat = overId === KCAT_NONE ? null : Number(overId.slice(KCAT_PREFIX.length));
        const dragData = active.data.current as { categoryId?: number | null } | undefined;
        const currentCat = dragData?.categoryId ?? null;
        if (currentCat === targetCat) return; // dropped back in same column
        haptic("success");
        void handleSetCategory(taskId, targetCat);
        return;
      }

      // Calendar day drop (Phase 7d): shift the task's due_at to the
      // target day, preserving its local time-of-day. The dragged row
      // carries its current due_at in the drag payload.
      if (overId.startsWith(CALDAY_PREFIX)) {
        const newKey = overId.slice(CALDAY_PREFIX.length);
        const dueAt = (active.data.current as { dueAt?: string | null } | undefined)?.dueAt;
        if (!dueAt) return;
        const oldKey = localDateKey(dueAt, tz);
        if (!oldKey || oldKey === newKey) return;
        const deltaDays = Math.round(
          (Date.parse(`${newKey}T00:00:00Z`) - Date.parse(`${oldKey}T00:00:00Z`)) / 86_400_000,
        );
        if (deltaDays === 0) return;
        const utc = dueAt.endsWith("Z") || dueAt.includes("+") ? dueAt : dueAt + "Z";
        const shifted = new Date(Date.parse(utc) + deltaDays * 86_400_000).toISOString();
        haptic("success");
        void handleReschedule(taskId, shifted);
        return;
      }

      // Horizon drop — pill in list view (Phase 5.4b). The drop id is a
      // bare horizon slug.
      const targetSlug = overId;
      if (!VALID_HORIZONS.has(targetSlug as HorizonSlug)) return;
      const dragData = active.data.current as { horizonSlug?: string } | undefined;
      const currentSlug = tasks.find((t) => t.id === taskId)?.horizon_slug ?? dragData?.horizonSlug;
      if (currentSlug === targetSlug) return; // no-op same horizon
      haptic("success");
      void handleMove(taskId, targetSlug as HorizonSlug);
    },
    [tasks, handleMove, handleReschedule, handleSetCategory, tz],
  );

  if (loading) {
    // Show the future shell (header + horizon tabs + task cards) as
    // outlines instantly. The user sees structure on the first frame
    // instead of a centred "Загружаем…", and the real layout drops in
    // without a shift when the API resolves.
    return <SkeletonAppShell />;
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

  // Detail page is a full-bleed overlay. We render it inside the same
  // DndContext so any open sheets share haptic/keyboard handling
  // (though dragging is disabled inside the detail screen).
  if (detailTaskId !== null) {
    return (
      <DndContext sensors={sensors}>
        <Suspense fallback={<ScreenFallback />}>
          <TaskDetail
            taskId={detailTaskId}
            tz={tz}
            horizons={horizons}
            categories={categories}
            onClose={handleCloseDetail}
            onMutated={handleDetailMutated}
            onDeleted={handleCloseDetail}
            onOptimisticDelete={handleTaskOptimisticDelete}
          />
        </Suspense>
        <BottomNav
          active={activeTab}
          onChange={setActiveTab}
          badges={{ inbox: inboxCount }}
        />
      </DndContext>
    );
  }

  if (noteRoute !== null) {
    return (
      <DndContext sensors={sensors}>
        <Suspense fallback={<ScreenFallback />}>
          <NoteDetail
            mode={noteRoute}
            categories={categories}
            onClose={handleCloseDetail}
            onMutated={handleNoteMutated}
            onDeleted={handleCloseDetail}
            onOptimisticDelete={handleNoteOptimisticDelete}
          />
        </Suspense>
        <BottomNav
          active={activeTab}
          onChange={(tab) => {
            navigateHome();
            setActiveTab(tab);
          }}
          badges={{ inbox: inboxCount }}
        />
      </DndContext>
    );
  }

  if (route.path === "/trash" || route.path === "/completed") {
    return (
      <DndContext sensors={sensors}>
        <div
          className="mx-auto max-w-md px-4"
          style={{
            paddingTop: "calc(var(--safe-top) + 0.75rem)",
            paddingBottom: "calc(var(--safe-bottom) + 5.5rem)",
          }}
        >
          <Suspense fallback={<ScreenFallback />}>
            {route.path === "/completed" ? <CompletedPage tz={tz} /> : <TrashPage />}
          </Suspense>
        </div>
        <BottomNav
          active={activeTab}
          onChange={(tab) => {
            navigateHome();
            setActiveTab(tab);
          }}
          badges={{ inbox: inboxCount }}
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
        : activeTab === "inbox"
          ? "Проверь, что распозналось"
          : undefined;

  const activeFilterLabel =
    selectedCategory === null
      ? undefined
      : categories.find((c) => c.id === selectedCategory)?.name;

  // Phase 7e/C linger: show open tasks + done ones completed within the
  // last 24h (struck-through). Older done tasks live in «Выполненные».
  // Plain const (not a hook) — we're past the early returns above.
  const LINGER_MS = 24 * 60 * 60 * 1000;
  const visibleTasks = tasks.filter((t) => {
    if (t.status !== "done") return true;
    // «Раскладка» → «Показывать выполненные» off: hide done entirely.
    if (!showCompleted) return false;
    const ts = t.completed_at;
    if (!ts) return false;
    // Server timestamps are naive UTC (no suffix); optimistic ones carry
    // a trailing Z. Normalise before parsing.
    const utc = ts.endsWith("Z") || ts.includes("+") ? ts : ts + "Z";
    return Date.now() - Date.parse(utc) < LINGER_MS;
  });

  // Phase 7e/F2: apply «Раскладка» filter → sort → group to the LIST view.
  // Pure transforms live in lib/layoutPrefs; we keep the (already
  // linger-filtered) ``visibleTasks`` as the input so done-task linger logic
  // stays intact. ``todayKey`` is the user's local "YYYY-MM-DD" for the due
  // filter. ``horizonLabels`` feeds friendly group headers in horizon mode.
  const todayKey = localDateKey(new Date().toISOString(), tz) ?? "";
  const horizonLabels: Record<string, string> = {};
  for (const h of horizons) horizonLabels[h.slug] = h.label;
  const taskGroups = groupTasks(
    applySort(
      applyFilters(
        visibleTasks,
        layoutPrefs.filterPriority,
        layoutPrefs.filterDue,
        tz,
        todayKey,
      ),
      layoutPrefs.sortBy,
    ),
    layoutPrefs.groupBy,
    horizonLabels,
  );
  const hasVisibleTasks = taskGroups.some((g) => g.tasks.length > 0);

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCorners}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
      onDragCancel={() => setActiveDragTask(null)}
    >
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
                  : activeTab === "inbox"
                    ? "Входящие"
                    : "Календарь"
          }
          subtitle={titleSubtitle}
          showFilter={activeTab === "tasks"}
          selectedCategoryId={selectedCategory}
          filterLabel={activeFilterLabel}
          onOpenFilter={() => setShowCategorySheet(true)}
          onOpenLayout={() => setShowLayoutSheet(true)}
          onOpenSearch={
            activeTab === "tasks"
              ? () => {
                  haptic("select");
                  setShowSearch(true);
                }
              : undefined
          }
          onCreate={activeTab === "notes" ? handleCreateNote : undefined}
          createLabel={activeTab === "notes" ? "Новая заметка" : undefined}
        />
        <div
          key={activeTab === "tasks" ? `tasks:${tasksView}` : activeTab}
          className="animate-tab-in"
        >
        <Suspense fallback={<ScreenFallback />}>
        {activeTab === "tasks" ? (
          <>
            {tasksView === "board" ? (
              <KanbanView
                categories={categories}
                refreshSignal={boardRefresh}
                optimisticMove={boardOptimistic}
                onOpen={handleOpenTask}
                onDone={handleDone}
                onCreateCategory={handleCreateCategoryColumn}
              />
            ) : (
              <>
                <HorizonTabs
                  horizons={horizons}
                  active={activeHorizon}
                  counts={counts}
                  onChange={handleHorizonChange}
                />
                {!hasVisibleTasks ? (
                  <EmptyState
                    icon={Sparkles}
                    tone="emerald"
                    title="Ничего на горизонте"
                    hint="Скинь голос или текст в бот — задачи появятся здесь автоматически."
                  />
                ) : layoutPrefs.groupBy === "none" ? (
                  <ul className="flex flex-col gap-2">
                    {taskGroups[0]?.tasks.map((task) => (
                      <li key={task.id}>
                        <TaskCard
                          task={task}
                          tz={tz}
                          onDone={handleDone}
                          onReopen={handleReopen}
                          onOpen={handleOpenTask}
                        />
                      </li>
                    ))}
                  </ul>
                ) : (
                  <div className="flex flex-col gap-5">
                    {taskGroups.map((group) => (
                      <section key={group.key}>
                        <header className="mb-2 px-1 text-[13px] font-semibold tracking-tight text-tg-link">
                          {group.label}
                        </header>
                        <ul className="flex flex-col gap-2">
                          {group.tasks.map((task) => (
                            <li key={task.id}>
                              <TaskCard
                                task={task}
                                tz={tz}
                                onDone={handleDone}
                                onReopen={handleReopen}
                                onOpen={handleOpenTask}
                              />
                            </li>
                          ))}
                        </ul>
                      </section>
                    ))}
                  </div>
                )}
              </>
            )}
          </>
        ) : activeTab === "notes" ? (
          <NotesList onOpen={handleOpenNote} />
        ) : activeTab === "calendar" ? (
          <CalendarView tz={tz} onOpen={handleOpenTask} />
        ) : activeTab === "inbox" ? (
          <InboxReview
            tz={tz}
            categories={categories}
            onResolved={() => {
              void loadInboxCount();
              void loadTasks(activeHorizon, selectedCategory);
              void loadCounts();
              void refreshCategories();
              invalidate(CAL_CACHE_PREFIX, { prefix: true });
              setBoardRefresh((n) => n + 1);
            }}
          />
        ) : me ? (
          <SettingsPage me={me} onUpdated={setMe} />
        ) : null}
        </Suspense>
        </div>
      </div>
      <CategoryFilter
        open={showCategorySheet}
        onClose={() => setShowCategorySheet(false)}
        categories={categories}
        selectedId={selectedCategory}
        onChange={handleCategoryChange}
      />
      <LayoutSheet
        open={showLayoutSheet}
        onClose={() => setShowLayoutSheet(false)}
        view={tasksView}
        onViewChange={(v) => {
          setTasksView(v);
          void storageSet(StorageKeys.lastTasksView, v);
        }}
        showCompleted={showCompleted}
        onShowCompletedChange={(next) => {
          setShowCompleted(next);
          void storageSet(StorageKeys.showCompleted, next ? "1" : "0");
        }}
        groupBy={layoutPrefs.groupBy}
        onGroupByChange={(groupBy) => updateLayoutPrefs({ groupBy })}
        sortBy={layoutPrefs.sortBy}
        onSortByChange={(sortBy) => updateLayoutPrefs({ sortBy })}
        filterPriority={layoutPrefs.filterPriority}
        onFilterPriorityChange={(filterPriority) =>
          updateLayoutPrefs({ filterPriority })
        }
        filterDue={layoutPrefs.filterDue}
        onFilterDueChange={(filterDue) => updateLayoutPrefs({ filterDue })}
        onResetAll={handleResetLayoutPrefs}
      />
      <BottomNav
        active={activeTab}
        onChange={setActiveTab}
        badges={{ inbox: inboxCount }}
      />
      <DragOverlay dropAnimation={null}>
        {activeDragTask ? <KanbanCardView task={activeDragTask} overlay /> : null}
      </DragOverlay>
      {showSearch && (
        <Suspense fallback={null}>
          <SearchOverlay
            tz={tz}
            onClose={() => setShowSearch(false)}
            onOpen={handleOpenTask}
          />
        </Suspense>
      )}
    </DndContext>
  );
}
