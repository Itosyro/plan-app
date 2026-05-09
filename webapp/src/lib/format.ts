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
