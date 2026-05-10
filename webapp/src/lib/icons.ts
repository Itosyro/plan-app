// Centralised icon mapping. Keep all lucide-react imports in one
// place so we can tree-shake aggressively and so component files
// reference our domain vocabulary, not raw lucide names.
//
// Style choice: lucide line-icons (24px stroke 1.5) match the
// minimal Todoist / Linear / Notion aesthetic the user asked for.
// Match `currentColor` so they auto-pick up Telegram-theme colors.

import {
  CalendarDays,
  CheckCircle2,
  Circle,
  ChevronRight,
  Clock,
  Flag,
  Inbox,
  ListTodo,
  Move,
  Settings,
  Sun,
  Sunrise,
  Sunset,
  Trash2,
  type LucideIcon,
} from "lucide-react";
import type { HorizonSlug, TaskPriority } from "../types";

// Per-horizon icon. Keep the mapping shallow — adding a new horizon
// without an icon falls back to ``Circle``.
export const HORIZON_ICONS: Record<HorizonSlug, LucideIcon> = {
  today: Sun,
  tomorrow: Sunrise,
  week: CalendarDays,
  month: CalendarDays,
  year: CalendarDays,
  someday: Sunset,
};

export function horizonIcon(slug: string | null | undefined): LucideIcon {
  if (slug && slug in HORIZON_ICONS) {
    return HORIZON_ICONS[slug as HorizonSlug];
  }
  return Circle;
}

// Priority icons. We intentionally use the same lucide ``Flag`` glyph
// for all three priorities and vary only the color via CSS class —
// keeps layout shifts to zero and matches Todoist's pattern.
export function priorityFlagColor(priority: TaskPriority): string {
  switch (priority) {
    case "high":
      return "text-red-500";
    case "medium":
      return "text-amber-500";
    case "low":
      return "text-emerald-500";
    default:
      return "text-tg-hint";
  }
}

export {
  CalendarDays,
  CheckCircle2,
  Circle,
  ChevronRight,
  Clock,
  Flag,
  Inbox,
  ListTodo,
  Move,
  Settings,
  Sun,
  Sunrise,
  Sunset,
  Trash2,
};
