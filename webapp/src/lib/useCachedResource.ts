// Unified data hook for the Mini-App.
//
// Replaces the per-screen pattern of:
//   const [data, setData] = useState(() => getCache(KEY) ?? null);
//   useEffect(() => { fetch().then(...).catch(...) }, [refreshSignal]);
//
// What it adds on top:
//   • Stale-while-revalidate: instant paint from the cache, fresh
//     data swaps in when the network lands.
//   • Smart skeleton: ``showSkeleton`` flips on only when there's
//     no cache AND the fetch takes longer than ~300ms — avoids the
//     skeleton flash on warm or fast loads.
//   • Optimistic ``mutate(updater)``: writes through to both the
//     component state and the underlying cache so other mounted
//     screens see the same optimistic value.
//   • Subscribes to the global cache bus: an ``invalidate`` in
//     another screen triggers a refetch here, a ``mutateCache``
//     repaints from the cache without touching the network —
//     dropping the nonce-prop chain that used to plumb refresh
//     signals through App.tsx.

import { useCallback, useEffect, useRef, useState } from "react";

import { getCache, setCache, subscribeInvalidate, type CacheEvent } from "./cache";

export interface CachedResource<T> {
  /** Last-known value. Cached entry on cold mount, fresh value
   *  after the fetch lands. ``undefined`` only when there is no
   *  cache and the first fetch hasn't finished. */
  data: T | undefined;
  /** ``true`` only when the first fetch is in flight AND took
   *  longer than ``skeletonDelayMs``. Use this for skeleton
   *  rendering; don't drive skeletons off ``data === undefined``
   *  alone or every warm load will flash. */
  showSkeleton: boolean;
  /** Error from the most recent fetch, cleared on the next
   *  successful refetch. */
  error: unknown;
  /** Trigger a network refetch without bumping any dep. */
  refetch: () => void;
  /** Optimistically write a new value. Mirrors React 18's
   *  ``setState`` updater signature; updates both component
   *  state AND the shared cache so other hooks pick it up. */
  mutate: (updater: (prev: T | undefined) => T) => void;
}

interface Options {
  /** How long to wait before flipping ``showSkeleton`` on a cold
   *  fetch. Default 300ms — fast networks never see a skeleton. */
  skeletonDelayMs?: number;
  /** When set, also subscribe to a prefix on the invalidation
   *  bus. Useful for CalendarView which keys by window
   *  (``cal:from:to``) but wants to refetch on any ``cal:`` bump. */
  invalidationPrefix?: string;
  /** When false, the fetcher never runs (and nothing is cached) —
   *  the hook just serves whatever the cache holds. Use to gate on
   *  auth / hydration instead of returning a fake empty value from
   *  the fetcher, which would poison the cache under a real key. */
  enabled?: boolean;
}

export function useCachedResource<T>(
  key: string,
  fetcher: () => Promise<T>,
  deps: ReadonlyArray<unknown>,
  opts: Options = {},
): CachedResource<T> {
  const { skeletonDelayMs = 300, invalidationPrefix, enabled = true } = opts;

  // Seed from cache so first paint shows last-known data without
  // a flash. Cache lookup is keyed by ``key`` so changing the key
  // (e.g. a calendar window) treats it as a different resource.
  const [data, setData] = useState<T | undefined>(() => getCache<T>(key));
  const [showSkeleton, setShowSkeleton] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [tick, setTick] = useState(0);

  // ``fetcher`` is recreated each render; pin it in a ref so the
  // effect deps stay primitive (key + tick + caller deps) and we
  // don't refetch on every render. Same pattern as setState in
  // a closure.
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  useEffect(() => {
    let cancelled = false;
    const cached = getCache<T>(key);
    // Repaint from cache on key change (new resource entirely).
    setData(cached);
    // Gated off (auth pending, prefs not hydrated): serve the cache,
    // skip the network. The effect re-runs when ``enabled`` flips on.
    if (!enabled) return;

    let skeletonTimer: number | undefined;
    if (cached === undefined) {
      skeletonTimer = window.setTimeout(() => {
        if (!cancelled) setShowSkeleton(true);
      }, skeletonDelayMs);
    }

    fetcherRef
      .current()
      .then((fresh) => {
        if (cancelled) return;
        setCache(key, fresh);
        setData(fresh);
        setError(null);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setError(e);
      })
      .finally(() => {
        if (cancelled) return;
        if (skeletonTimer !== undefined) window.clearTimeout(skeletonTimer);
        setShowSkeleton(false);
      });

    return () => {
      cancelled = true;
      if (skeletonTimer !== undefined) window.clearTimeout(skeletonTimer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, tick, enabled, ...deps]);

  // Wake up on bus pings. Both an exact-key bus entry and an optional
  // prefix subscription are honoured; the hook owner picks which
  // (calendar wants prefix, notes want exact). A "mutate" ping means
  // the cache already holds the optimistic value — repaint from it,
  // never refetch (the GET would race the in-flight PATCH/DELETE and
  // could overwrite the optimistic state with pre-mutation data).
  // Only "invalidate" triggers a network refetch.
  useEffect(() => {
    const onEvent = (event: CacheEvent) => {
      if (event === "mutate") {
        const cached = getCache<T>(key);
        // Missing entry (e.g. dropped by a concurrent invalidate):
        // keep showing what we have, the refetch is already queued.
        if (cached !== undefined) setData(cached);
        return;
      }
      setTick((n) => n + 1);
    };
    const unsubExact = subscribeInvalidate(key, onEvent);
    if (invalidationPrefix === undefined) {
      return unsubExact;
    }
    const unsubPrefix = subscribeInvalidate(invalidationPrefix, onEvent, {
      prefix: true,
    });
    return () => {
      unsubExact();
      unsubPrefix();
    };
  }, [key, invalidationPrefix]);

  const refetch = useCallback(() => {
    setTick((n) => n + 1);
  }, []);

  const mutate = useCallback(
    (updater: (prev: T | undefined) => T) => {
      setData((prev) => {
        const next = updater(prev);
        setCache(key, next);
        return next;
      });
    },
    [key],
  );

  return { data, showSkeleton, error, refetch, mutate };
}
