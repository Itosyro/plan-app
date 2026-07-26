// Tiny in-memory stale-while-revalidate cache + invalidation bus.
//
// The cache itself is a module-scoped Map: it survives component
// unmount/remount (e.g. tab switching) but resets on a full WebView
// reload. The bus on top lets a mutation in one screen mark another
// screen's cache stale and wake any mounted ``useCachedResource``
// hook listening on that key — replacing the ad-hoc nonce-prop
// chain (notesRefresh / boardRefresh / calendarRefresh) that used
// to thread refresh signals through App.tsx.
//
// Two flavours of invalidation:
//   • exact key:   ``invalidate("notes")``
//   • prefix:      ``invalidate("cal:", { prefix: true })``
// Prefix is the easy answer to the CalendarView cache where every
// visited window is a separate ``cal:{from}:{to}`` entry — one
// reschedule should clear them all.

const store = new Map<string, unknown>();

// What a listener ping means:
//   "mutate"     — the cache already holds the new value; repaint from
//                  it, do NOT refetch (a GET here would race the still
//                  in-flight PATCH/DELETE and could resurrect
//                  pre-mutation data).
//   "invalidate" — the entry was dropped; refetch from the network.
export type CacheEvent = "mutate" | "invalidate";
type Listener = (event: CacheEvent) => void;
const exactListeners = new Map<string, Set<Listener>>();
const prefixListeners = new Map<string, Set<Listener>>();

export function getCache<T>(key: string): T | undefined {
  return store.get(key) as T | undefined;
}

export function setCache<T>(key: string, value: T): void {
  store.set(key, value);
}

interface InvalidateOpts {
  /** When true, ``key`` is a prefix — every cache entry whose key
   *  starts with it is dropped, and every listener whose subscribed
   *  key starts with it (or vice-versa) is notified. */
  prefix?: boolean;
}

export function invalidate(key: string, opts: InvalidateOpts = {}): void {
  if (opts.prefix) {
    for (const k of [...store.keys()]) {
      if (k.startsWith(key)) store.delete(k);
    }
    // Notify both exact listeners under the prefix AND any prefix-
    // subscribed listener that overlaps. The two-way overlap check
    // covers the case where a hook subscribes with prefix "cal:" and
    // a mutation invalidates the more specific "cal:2026-05".
    for (const [listenerKey, set] of exactListeners) {
      if (listenerKey.startsWith(key)) {
        for (const fn of set) fn("invalidate");
      }
    }
    for (const [listenerPrefix, set] of prefixListeners) {
      if (listenerPrefix.startsWith(key) || key.startsWith(listenerPrefix)) {
        for (const fn of set) fn("invalidate");
      }
    }
    return;
  }
  store.delete(key);
  exactListeners.get(key)?.forEach((fn) => fn("invalidate"));
  for (const [listenerPrefix, set] of prefixListeners) {
    if (key.startsWith(listenerPrefix)) {
      for (const fn of set) fn("invalidate");
    }
  }
}

// Optimistic write-through. Updates the cached value and pings any
// listeners on ``key`` so a mounted ``useCachedResource`` hook
// repaints from the new cache immediately. Use for cross-screen
// optimism: e.g. App.tsx drops a note from the cache the instant
// the detail view confirms a delete, before the NotesList component
// even owns that mutation. The hook's own ``mutate`` is the same
// thing reached from inside a single screen.
export function mutateCache<T>(
  key: string,
  updater: (prev: T | undefined) => T,
  opts: InvalidateOpts = {},
): void {
  if (opts.prefix) {
    // Prefix mutate: apply ``updater`` to every existing entry
    // whose key starts with ``key``. Skips keys without an entry —
    // the typical use is "after a task reschedule, patch every
    // already-cached calendar window in place". A new window that
    // wasn't visited yet has no entry to patch and will fetch
    // fresh on its first mount anyway.
    for (const k of [...store.keys()]) {
      if (!k.startsWith(key)) continue;
      const next = updater(store.get(k) as T | undefined);
      store.set(k, next);
      exactListeners.get(k)?.forEach((fn) => fn("mutate"));
    }
    for (const [listenerPrefix, set] of prefixListeners) {
      if (listenerPrefix.startsWith(key) || key.startsWith(listenerPrefix)) {
        for (const fn of set) fn("mutate");
      }
    }
    return;
  }
  const next = updater(store.get(key) as T | undefined);
  store.set(key, next);
  exactListeners.get(key)?.forEach((fn) => fn("mutate"));
  for (const [listenerPrefix, set] of prefixListeners) {
    if (key.startsWith(listenerPrefix)) {
      for (const fn of set) fn("mutate");
    }
  }
}

export function subscribeInvalidate(
  key: string,
  fn: Listener,
  opts: InvalidateOpts = {},
): () => void {
  const bucket = opts.prefix ? prefixListeners : exactListeners;
  let set = bucket.get(key);
  if (set === undefined) {
    set = new Set();
    bucket.set(key, set);
  }
  set.add(fn);
  return () => {
    set.delete(fn);
    if (set.size === 0) bucket.delete(key);
  };
}

// Test / debug hooks. ``clearCacheForTests`` resets all module
// state — the cache, both listener buckets — so a test can start
// from a known-empty slate without leaking subscriptions across
// test cases.
export function clearCacheForTests(): void {
  store.clear();
  exactListeners.clear();
  prefixListeners.clear();
}
