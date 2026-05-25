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
