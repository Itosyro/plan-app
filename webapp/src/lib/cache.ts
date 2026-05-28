// Tiny in-memory stale-while-revalidate cache. Module-scoped, so it
// survives component unmount/remount (e.g. switching tabs) but resets
// on a full WebView reload. Lets a view render its last-known data
// instantly on re-entry instead of flashing a spinner while the network
// round-trips — the fetch still runs and replaces the data when it lands.
const store = new Map<string, unknown>();

export function getCache<T>(key: string): T | undefined {
  return store.get(key) as T | undefined;
}

export function setCache<T>(key: string, value: T): void {
  store.set(key, value);
}
