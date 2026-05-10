// Shared TypeScript types — mirrored from app/api/schemas.py.
// Keep these in sync; a CI-time codegen step is on the roadmap (Phase 5.4).

export type HorizonSlug = "today" | "tomorrow" | "week" | "month" | "year" | "someday";
export type TaskStatus = "new" | "in_progress" | "done" | "cancelled";
export type TaskPriority = "low" | "medium" | "high";

export interface Horizon {
  slug: string;
  label: string;
}

export interface Category {
  id: number;
  name: string;
  task_count: number;
}

export interface Task {
  id: number;
  title: string;
  description: string | null;
  priority: TaskPriority;
  status: TaskStatus;
  due_at: string | null;
  created_at: string;
  horizon_slug: HorizonSlug | null;
  category_id: number | null;
  category_name: string | null;
}

export interface Note {
  id: number;
  title: string;
  body: string | null;
  category_id: number | null;
  category_name: string | null;
  created_at: string;
}

export interface UserSettings {
  critic_mode: string;
  morning_digest_at: string;
  evening_digest_at: string;
  response_style_source: string;
  courier_template_style: string;
  week_due_semantic: string;
}

export interface Me {
  id: number;
  telegram_id: number;
  display_name: string | null;
  tz: string;
  onboarded: boolean;
  settings: UserSettings | null;
}

export interface TaskUpdate {
  title?: string;
  status?: TaskStatus;
  priority?: TaskPriority;
  horizon_slug?: HorizonSlug;
  category_id?: number;
  due_at?: string;
}

// Mirrors app/api/schemas.py::TaskCountsOut. One bucket per horizon
// plus ``no_horizon`` for legacy tasks. ``done`` and ``cancelled``
// are excluded server-side.
export interface TaskCounts {
  today: number;
  tomorrow: number;
  week: number;
  month: number;
  year: number;
  someday: number;
  no_horizon: number;
}
