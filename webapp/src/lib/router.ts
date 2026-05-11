// Minimal hash-based router for the Mini-App.
//
// Why not ``react-router-dom``? Three reasons:
//
//   1. The Mini-App ships in a Telegram WebView whose URL is fixed
//      (``/app``). We never round-trip the URL — only the in-memory
//      hash matters, and that hash never reaches the server.
//   2. Telegram's WebApp SDK overrides ``history.pushState`` in
//      some clients, so a real router would either fight it or
//      need a custom history adapter. Hash routing sidesteps both.
//   3. The whole router fits in ~50 lines. Pulling in react-router-dom
//      would add ~50 KB gzipped for one screen of routing.
//
// API:
//
//   const route = useRoute();           // {path: "/task/:id" | "/", params: {id}}
//   navigate("/task/123")               // sets location.hash = "#/task/123"
//   navigate("/")                       // sets location.hash = "#/"
//
// Supported patterns: ``/``, ``/task/:id``. Add more in ``ROUTES``.

import { useEffect, useState } from "react";

const ROUTES: { pattern: RegExp; path: string; keys: string[] }[] = [
  // Order matters: more specific routes first.
  { pattern: /^\/task\/(\d+)$/, path: "/task/:id", keys: ["id"] },
  { pattern: /^\/$/, path: "/", keys: [] },
];

export interface Route {
  path: string;
  params: Record<string, string>;
}

const HOME: Route = { path: "/", params: {} };

function parseHash(hash: string): Route {
  // Strip leading ``#`` and ensure leading ``/``.
  const raw = hash.replace(/^#/, "") || "/";
  const normalized = raw.startsWith("/") ? raw : "/" + raw;
  for (const route of ROUTES) {
    const m = normalized.match(route.pattern);
    if (m) {
      const params: Record<string, string> = {};
      route.keys.forEach((key, i) => {
        const value = m[i + 1];
        if (typeof value === "string") params[key] = value;
      });
      return { path: route.path, params };
    }
  }
  return HOME;
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() =>
    typeof window === "undefined" ? HOME : parseHash(window.location.hash),
  );
  useEffect(() => {
    if (typeof window === "undefined") return;
    const onChange = () => {
      setRoute(parseHash(window.location.hash));
    };
    window.addEventListener("hashchange", onChange);
    return () => {
      window.removeEventListener("hashchange", onChange);
    };
  }, []);
  return route;
}

export function navigate(path: string): void {
  if (typeof window === "undefined") return;
  const normalized = path.startsWith("/") ? path : "/" + path;
  const target = "#" + normalized;
  if (window.location.hash === target) return;
  window.location.hash = target;
}

export function navigateHome(): void {
  navigate("/");
}
