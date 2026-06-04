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
  // When the FirstStep rewrite kicked in, ``title`` holds the actionable
  // rewrite and ``title_original`` carries the user's original abstract
  // phrasing. Null for tasks that weren't rewritten.
  title_original: string | null;
  description: string | null;
  priority: TaskPriority;
  status: TaskStatus;
  due_at: string | null;
  created_at: string;
  // Phase 7e/C: set when marked done (cleared on reopen). Drives the
  // "Выполненные" screen + linger-strikethrough window. Null when open.
  completed_at: string | null;
  horizon_slug: HorizonSlug | null;
  category_id: number | null;
  category_name: string | null;
  // Subtasks: ``parent_id`` is set on child rows (top-level tasks have
  // ``null``). ``subtasks_total`` / ``subtasks_done`` are computed
  // server-side for list endpoints so the UI can render a "1/3" chip
  // without fetching children.
  parent_id: number | null;
  subtasks_total: number;
  subtasks_done: number;
}

// Returned by ``GET /api/tasks/{id}``: full parent + hydrated children.
export interface TaskDetail extends Task {
  subtasks: Task[];
}

export interface Note {
  id: number;
  title: string;
  body: string | null;
  category_id: number | null;
  category_name: string | null;
  created_at: string;
}

// Mirrors app/api/schemas.py::NoteCreateIn.
export interface NoteCreate {
  title: string;
  body?: string | null;
  category_id?: number | null;
}

// Mirrors app/api/schemas.py::NoteUpdateIn — every field optional.
export interface NoteUpdate {
  title?: string;
  body?: string | null;
  category_id?: number | null;
}

export interface UserSettings {
  critic_mode: string;
  morning_digest_at: string;
  evening_digest_at: string;
  response_style_source: string;
  courier_template_style: string;
  week_due_semantic: string;
  // PR-E "make it concrete": when true, the classifier's optional
  // ``first_step`` text is prepended to ``Task.description`` as
  // "Шаг 1: …". Defaults to false server-side.
  concretize_tasks: boolean;
  // When true, uncertain/large breakdowns are routed to the «Входящие»
  // review tab instead of being applied directly. Defaults to true.
  review_enabled: boolean;
  // WS4: default reminder advance offsets (minutes before ``due_at``).
  // ``same_day`` applies to tasks due today, ``multi_day`` to tasks
  // due tomorrow or later. Server keeps each list sorted descending
  // (earliest reminder first) and bounded to 5 entries × 0..10080 min.
  default_reminder_offsets: {
    same_day: number[];
    multi_day: number[];
  };
}

// Mirrors app/api/schemas.py::UserSettingsUpdateIn — every field
// optional. Server validates each value against the allow-list in
// app/bot/services/settings.py::ALLOWED_SETTING_VALUES.
export interface UserSettingsUpdate {
  critic_mode?: string;
  morning_digest_at?: string;
  evening_digest_at?: string;
  response_style_source?: string;
  courier_template_style?: string;
  week_due_semantic?: string;
  concretize_tasks?: boolean;
  review_enabled?: boolean;
  default_reminder_offsets?: {
    same_day: number[];
    multi_day: number[];
  };
}

// Mirrors app/api/schemas.py::MeUpdateIn.
export interface MeUpdate {
  display_name?: string;
  tz?: string;
  settings?: UserSettingsUpdate;
}

// Mirrors app/api/schemas.py::TimezoneOut. ``label`` is the friendly
// Russian city name; ``iana`` is the persisted value.
export interface Timezone {
  label: string;
  iana: string;
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
  description?: string | null;
  status?: TaskStatus;
  priority?: TaskPriority;
  horizon_slug?: HorizonSlug;
  category_id?: number | null;
  due_at?: string | null;
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

// ── Trash ───────────────────────────────────────────────────────────

export type TrashKind = "task" | "note";

export interface TrashItem {
  id: number;
  kind: TrashKind;
  title: string;
  deleted_at: string;
  category_name: string | null;
}

export interface TrashCounts {
  tasks: number;
  notes: number;
}

// ── Входящие (review inbox) ─────────────────────────────────────────
// Mirrors app/api/schemas.py::InboxReviewOut. One inbox entry that the
// pipeline flagged for review, with the top-level tasks it produced.
// ``text`` is the user-facing source (transcript for voice, raw_text for
// text). The user keeps the checked tasks and drops the rest on confirm.
export interface InboxReview {
  id: number;
  kind: string;
  text: string | null;
  received_at: string;
  tasks: Task[];
  notes: Note[];
}

// ── Доски (Excalidraw canvases) ─────────────────────────────────────
// Mirrors app/api/schemas.py::BoardOut (light list item — no scene_json).
export interface Board {
  id: number;
  name: string;
  created_at: string;
  updated_at: string;
}

// Mirrors app/api/schemas.py::BoardDetailOut — full record with scene.
export interface BoardDetail extends Board {
  scene_json: Record<string, unknown> | null;
}
