// Small helpers for rendering. Keep dependency-free.

export function formatDue(iso: string | null, tz: string): string | null {
  if (!iso) return null;
  // The backend returns naive UTC strings ("2026-05-09T18:30:00") — append
  // ``Z`` so JS parses them as UTC, then format in the user's tz.
  const utc = iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z";
  const date = new Date(utc);
  if (Number.isNaN(date.getTime())) return null;
  try {
    return new Intl.DateTimeFormat("ru-RU", {
      timeZone: tz,
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    }).format(date);
  } catch {
    return new Intl.DateTimeFormat("ru-RU", {
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    }).format(date);
  }
}

export function priorityIcon(priority: string): string {
  switch (priority) {
    case "high":
      return "🔴";
    case "medium":
      return "🟡";
    case "low":
      return "🟢";
    default:
      return "⚪";
  }
}

// Local calendar-day key ("YYYY-MM-DD") for a naive-UTC ISO string,
// resolved in the user's timezone. Used to bucket tasks into calendar
// cells so a task due 23:30 local doesn't leak into the next UTC day.
export function localDateKey(iso: string | null, tz: string): string | null {
  if (!iso) return null;
  const utc = iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z";
  const date = new Date(utc);
  if (Number.isNaN(date.getTime())) return null;
  try {
    // en-CA gives ISO-ordered "YYYY-MM-DD".
    return new Intl.DateTimeFormat("en-CA", {
      timeZone: tz,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(date);
  } catch {
    return new Intl.DateTimeFormat("en-CA", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(date);
  }
}

// "HH:MM" local time for a naive-UTC ISO string. Null when no time.
export function localTime(iso: string | null, tz: string): string | null {
  if (!iso) return null;
  const utc = iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z";
  const date = new Date(utc);
  if (Number.isNaN(date.getTime())) return null;
  try {
    return new Intl.DateTimeFormat("ru-RU", {
      timeZone: tz,
      hour: "2-digit",
      minute: "2-digit",
    }).format(date);
  } catch {
    return new Intl.DateTimeFormat("ru-RU", {
      hour: "2-digit",
      minute: "2-digit",
    }).format(date);
  }
}

// Deterministic category color for calendar event pills. A fixed soft
// palette indexed by category id (no DB field needed). ``null`` (no
// category) gets a neutral slate. Returns {dot, pill, text} Tailwind
// classes so callers don't string-concat colors (Tailwind keeps them).
const CATEGORY_PALETTE: { dot: string; pill: string; text: string }[] = [
  { dot: "bg-blue-500", pill: "bg-blue-500/12", text: "text-blue-700" },
  { dot: "bg-emerald-500", pill: "bg-emerald-500/12", text: "text-emerald-700" },
  { dot: "bg-orange-500", pill: "bg-orange-500/12", text: "text-orange-700" },
  { dot: "bg-violet-500", pill: "bg-violet-500/12", text: "text-violet-700" },
  { dot: "bg-rose-500", pill: "bg-rose-500/12", text: "text-rose-700" },
  { dot: "bg-teal-500", pill: "bg-teal-500/12", text: "text-teal-700" },
  { dot: "bg-amber-500", pill: "bg-amber-500/12", text: "text-amber-700" },
  { dot: "bg-indigo-500", pill: "bg-indigo-500/12", text: "text-indigo-700" },
];
const NEUTRAL = { dot: "bg-slate-400", pill: "bg-slate-400/12", text: "text-slate-600" };

export function categoryColor(id: number | null): {
  dot: string;
  pill: string;
  text: string;
} {
  if (id === null) return NEUTRAL;
  return CATEGORY_PALETTE[id % CATEGORY_PALETTE.length];
}
