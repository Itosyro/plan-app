// Shared task-priority option constants. Used by both the full task
// detail page (TaskDetail) and the inbox review card (InboxReview) so
// the picker options / labels stay in one place.

import type { TaskPriority } from "../types";

export const PRIORITY_OPTIONS: { value: TaskPriority; label: string; hint?: string }[] = [
  { value: "high", label: "Высокий", hint: "Срочно, важно" },
  { value: "medium", label: "Средний", hint: "По умолчанию" },
  { value: "low", label: "Низкий", hint: "Когда будет время" },
];

export const PRIORITY_LABEL: Record<TaskPriority, string> = {
  high: "Высокий",
  medium: "Средний",
  low: "Низкий",
};
