export function todayStart(tz = 'Europe/Moscow'): Date {
  const now = new Date();
  const formatter = new Intl.DateTimeFormat('en-CA', { timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit' });
  const dateStr = formatter.format(now);
  return new Date(dateStr + 'T00:00:00.000Z');
}

export function tomorrowStart(tz = 'Europe/Moscow'): Date {
  const d = todayStart(tz);
  d.setDate(d.getDate() + 1);
  return d;
}

export function parseRelativeDate(label: string, tz = 'Europe/Moscow'): Date | null {
  const lower = label.toLowerCase().trim();
  if (lower.includes('сегодня') || lower === 'today') return todayStart(tz);
  if (lower.includes('послезавтра')) {
    const d = todayStart(tz);
    d.setDate(d.getDate() + 2);
    return d;
  }
  if (lower.includes('завтра') || lower === 'tomorrow') return tomorrowStart(tz);
  if (lower.includes('на неделе') || lower.includes('эта неделя') || lower === 'this week') {
    const d = todayStart(tz);
    const dayOfWeek = d.getDay();
    const daysUntilFriday = (5 - dayOfWeek + 7) % 7 || 7;
    d.setDate(d.getDate() + daysUntilFriday);
    return d;
  }
  return null;
}

export function formatDate(date: Date, tz = 'Europe/Moscow'): string {
  return new Intl.DateTimeFormat('ru-RU', {
    timeZone: tz,
    day: 'numeric',
    month: 'long',
  }).format(date);
}
