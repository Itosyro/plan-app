// Fetch wrapper that auto-injects ``X-Telegram-Init-Data`` and JSON-decodes.
//
// All API requests go through ``api()`` so:
//  1. The init-data header is added in one place.
//  2. Non-2xx responses raise typed errors instead of returning `Response`.
//  3. JSON parsing is centralised (incl. 204 No Content for DELETE).

import { getWebApp } from "../lib/telegram";

const API_BASE = "/api";

export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(status: number, body: unknown, message: string) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

interface ApiOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined>;
}

function buildUrl(path: string, query?: ApiOptions["query"]): string {
  const url = new URL(API_BASE + path, window.location.origin);
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v === undefined || v === null) continue;
      url.searchParams.set(k, String(v));
    }
  }
  return url.toString();
}

export async function api<T>(path: string, opts: ApiOptions = {}): Promise<T> {
  const wa = getWebApp();
  const headers: Record<string, string> = {
    Accept: "application/json",
  };
  if (wa?.initData) {
    headers["X-Telegram-Init-Data"] = wa.initData;
  }
  let body: BodyInit | undefined;
  if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  const resp = await fetch(buildUrl(path, opts.query), {
    method: opts.method ?? "GET",
    headers,
    body,
  });
  if (resp.status === 204) {
    return undefined as T;
  }
  let parsed: unknown = null;
  const text = await resp.text();
  if (text) {
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = text;
    }
  }
  if (!resp.ok) {
    const detail =
      parsed && typeof parsed === "object" && parsed !== null && "detail" in parsed
        ? String((parsed as { detail: unknown }).detail)
        : `HTTP ${resp.status}`;
    throw new ApiError(resp.status, parsed, detail);
  }
  return parsed as T;
}

// ── Typed convenience wrappers ──────────────────────────────────────

import type {
  Category,
  Horizon,
  Me,
  MeUpdate,
  Note,
  Task,
  TaskCounts,
  TaskUpdate,
  Timezone,
} from "../types";

export const apiClient = {
  me: () => api<Me>("/me"),
  patchMe: (body: MeUpdate) => api<Me>("/me", { method: "PATCH", body }),
  timezones: () => api<Timezone[]>("/timezones"),
  horizons: () => api<Horizon[]>("/horizons"),
  categories: () => api<Category[]>("/categories"),
  createCategory: (name: string) =>
    api<Category>("/categories", { method: "POST", body: { name } }),
  tasks: (q?: { horizon?: string; category_id?: number; status?: string; include_done?: boolean }) =>
    api<Task[]>("/tasks", { query: q }),
  taskCounts: () => api<TaskCounts>("/tasks/counts"),
  task: (id: number) => api<Task>(`/tasks/${id}`),
  patchTask: (id: number, body: TaskUpdate) =>
    api<Task>(`/tasks/${id}`, { method: "PATCH", body }),
  deleteTask: (id: number) => api<void>(`/tasks/${id}`, { method: "DELETE" }),
  notes: () => api<Note[]>("/notes"),
};
