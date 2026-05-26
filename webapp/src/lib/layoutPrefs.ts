// Phase 7e/F2: «Раскладка» list prefs — grouping / sorting / filtering for
// the Tasks LIST view. Persisted as one JSON blob under
// StorageKeys.layoutPrefs to economise on Telegram's per-bot key quota.
//
// Everything here is dependency-free and pure: parse/validate the stored
// blob, and apply group/sort/filter over a task array. App.tsx owns the
// state + persistence; this module owns the (testable) transforms.

import type { Task } from "../types";
import { localDateKey } from "./format";

export type GroupBy = "none" | "category" | "priority" | "horizon";
export type SortBy = "manual" | "date" | "priority" | "alpha";
export type FilterPriority = "all" | "high" | "medium" | "low";
export type FilterDue = "all" | "overdue" | "today" | "week";

export interface LayoutPrefs {
  groupBy: GroupBy;
  sortBy: SortBy;
  filterPriority: FilterPriority;
  filterDue: FilterDue;
}

export const DEFAULT_LAYOUT_PREFS: LayoutPrefs = {
  groupBy: "none",
  sortBy: "manual",
  filterPriority: "all",
  filterDue: "all",
};

const GROUP_VALUES: ReadonlySet<string> = new Set([
  "none",
  "category",
  "priority",
  "horizon",
]);
const SORT_VALUES: ReadonlySet<string> = new Set([
  "manual",
  "date",
  "priority",
  "alpha",
]);
const PRIORITY_VALUES: ReadonlySet<string> = new Set([
  "all",
  "high",
  "medium",
  "low",
]);
const DUE_VALUES: ReadonlySet<string> = new Set([
  "all",
  "overdue",
  "today",
  "week",
]);

// Parse the stored JSON blob, falling back to defaults for any missing or
// invalid field. Never throws — bad data just yields defaults.
export function parseLayoutPrefs(raw: string | null): LayoutPrefs {
  if (!raw) return { ...DEFAULT_LAYOUT_PREFS };
  try {
    const obj = JSON.parse(raw) as Record<string, unknown>;
    return {
      groupBy: GROUP_VALUES.has(obj.groupBy as string)
        ? (obj.groupBy as GroupBy)
        : DEFAULT_LAYOUT_PREFS.groupBy,
      sortBy: SORT_VALUES.has(obj.sortBy as string)
        ? (obj.sortBy as SortBy)
        : DEFAULT_LAYOUT_PREFS.sortBy,
      filterPriority: PRIORITY_VALUES.has(obj.filterPriority as string)
        ? (obj.filterPriority as FilterPriority)
        : DEFAULT_LAYOUT_PREFS.filterPriority,
      filterDue: DUE_VALUES.has(obj.filterDue as string)
        ? (obj.filterDue as FilterDue)
        : DEFAULT_LAYOUT_PREFS.filterDue,
    };
  } catch {
    return { ...DEFAULT_LAYOUT_PREFS };
  }
}

export function serializeLayoutPrefs(prefs: LayoutPrefs): string {
  return JSON.stringify(prefs);
}

export function isDefaultLayoutPrefs(prefs: LayoutPrefs): boolean {
  return (
    prefs.groupBy === DEFAULT_LAYOUT_PREFS.groupBy &&
    prefs.sortBy === DEFAULT_LAYOUT_PREFS.sortBy &&
    prefs.filterPriority === DEFAULT_LAYOUT_PREFS.filterPriority &&
    prefs.filterDue === DEFAULT_LAYOUT_PREFS.filterDue
  );
}

// ── Filter ────────────────────────────────────────────────────────────

const PRIORITY_RANK: Record<string, number> = { high: 0, medium: 1, low: 2 };

// Apply the priority + due filters. ``todayKey`` is "YYYY-MM-DD" for the
// user's local today (caller computes it once via localDateKey(now, tz)).
export function applyFilters(
  tasks: Task[],
  filterPriority: FilterPriority,
  filterDue: FilterDue,
  tz: string,
  todayKey: string,
): Task[] {
  if (filterPriority === "all" && filterDue === "all") return tasks;
  return tasks.filter((t) => {
    if (filterPriority !== "all" && t.priority !== filterPriority) return false;
    if (filterDue !== "all") {
      const key = localDateKey(t.due_at, tz);
      if (!key) return false; // no due date → excluded from any date filter
      if (filterDue === "overdue" && !(key < todayKey)) return false;
      if (filterDue === "today" && key !== todayKey) return false;
      if (filterDue === "week") {
        // today .. today+6 inclusive (the next 7 days, today included)
        const end = addDaysKey(todayKey, 6);
        if (key < todayKey || key > end) return false;
      }
    }
    return true;
  });
}

// Add ``days`` to a "YYYY-MM-DD" key, returning a new key. Uses UTC math
// on the bare date so DST never shifts the result.
function addDaysKey(key: string, days: number): string {
  const ms = Date.parse(`${key}T00:00:00Z`) + days * 86_400_000;
  return new Date(ms).toISOString().slice(0, 10);
}

// ── Sort ──────────────────────────────────────────────────────────────

// Stable sort over a copy. ``manual`` returns the input order untouched.
export function applySort(tasks: Task[], sortBy: SortBy): Task[] {
  if (sortBy === "manual") return tasks;
  const copy = [...tasks];
  if (sortBy === "date") {
    copy.sort((a, b) => {
      // nulls last
      if (a.due_at === null && b.due_at === null) return 0;
      if (a.due_at === null) return 1;
      if (b.due_at === null) return -1;
      return a.due_at < b.due_at ? -1 : a.due_at > b.due_at ? 1 : 0;
    });
  } else if (sortBy === "priority") {
    copy.sort(
      (a, b) =>
        (PRIORITY_RANK[a.priority] ?? 3) - (PRIORITY_RANK[b.priority] ?? 3),
    );
  } else if (sortBy === "alpha") {
    copy.sort((a, b) => a.title.localeCompare(b.title, "ru"));
  }
  return copy;
}

// ── Group ─────────────────────────────────────────────────────────────

export interface TaskGroup {
  key: string;
  label: string;
  tasks: Task[];
}

const PRIORITY_LABEL: Record<string, string> = {
  high: "Высокий приоритет",
  medium: "Средний приоритет",
  low: "Низкий приоритет",
};
const PRIORITY_ORDER = ["high", "medium", "low"];

// Group an already-filtered+sorted task list. Returns a single anonymous
// group when ``groupBy === "none"`` so callers can render uniformly.
// ``horizonLabels`` maps a horizon slug → friendly label (from the API).
export function groupTasks(
  tasks: Task[],
  groupBy: GroupBy,
  horizonLabels: Record<string, string>,
): TaskGroup[] {
  if (groupBy === "none") {
    return [{ key: "__all__", label: "", tasks }];
  }

  const buckets = new Map<string, TaskGroup>();
  const order: string[] = [];
  const push = (key: string, label: string, task: Task) => {
    let g = buckets.get(key);
    if (!g) {
      g = { key, label, tasks: [] };
      buckets.set(key, g);
      order.push(key);
    }
    g.tasks.push(task);
  };

  for (const t of tasks) {
    if (groupBy === "category") {
      const key = t.category_id === null ? "__none__" : `c${t.category_id}`;
      const label = t.category_name ?? "Без раздела";
      push(key, label, t);
    } else if (groupBy === "priority") {
      const key = t.priority;
      push(key, PRIORITY_LABEL[key] ?? "Без приоритета", t);
    } else {
      // horizon
      const slug = t.horizon_slug;
      const key = slug === null ? "__none__" : slug;
      const label = slug === null ? "Без горизонта" : horizonLabels[slug] ?? slug;
      push(key, label, t);
    }
  }

  // Priority groups get a meaningful high→low order; others keep
  // first-seen (which respects the upstream sort).
  if (groupBy === "priority") {
    return PRIORITY_ORDER.map((k) => buckets.get(k)).filter(
      (g): g is TaskGroup => g !== undefined,
    );
  }
  return order.map((k) => buckets.get(k)!);
}
