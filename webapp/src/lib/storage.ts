// Unified async storage with Telegram CloudStorage primary, localStorage
// fallback. CloudStorage syncs across the user's Telegram clients (phone,
// desktop, tablet) without a backend roundtrip — perfect for tiny UI
// preferences. Older Telegram clients (or non-Telegram envs like local
// dev) silently fall through to localStorage.

import { getWebApp } from "./telegram";

const KEY_PREFIX = "plan_";
const KEY_RE = /^[A-Za-z0-9_-]{1,128}$/;

function fullKey(key: string): string {
  return `${KEY_PREFIX}${key}`;
}

function getCloudStorage() {
  const wa = getWebApp();
  return wa?.CloudStorage ?? null;
}

function safeLocalStorage(): Storage | null {
  try {
    if (typeof window === "undefined") return null;
    const ls = window.localStorage;
    // Probe so we don't trip over Safari private mode / disabled storage.
    const probe = `${KEY_PREFIX}__probe__`;
    ls.setItem(probe, "1");
    ls.removeItem(probe);
    return ls;
  } catch {
    return null;
  }
}

export async function storageGet(key: string): Promise<string | null> {
  if (!KEY_RE.test(fullKey(key))) return null;
  const cloud = getCloudStorage();
  if (cloud) {
    return new Promise((resolve) => {
      cloud.getItem(fullKey(key), (err, value) => {
        if (err) {
          // Fall back to local storage on any error.
          const ls = safeLocalStorage();
          resolve(ls?.getItem(fullKey(key)) ?? null);
          return;
        }
        // CloudStorage returns "" for missing keys — normalise to null.
        resolve(value || null);
      });
    });
  }
  const ls = safeLocalStorage();
  return ls?.getItem(fullKey(key)) ?? null;
}

export async function storageSet(key: string, value: string): Promise<boolean> {
  if (!KEY_RE.test(fullKey(key))) return false;
  if (value.length > 4096) return false; // Telegram cap
  const cloud = getCloudStorage();
  if (cloud) {
    return new Promise((resolve) => {
      cloud.setItem(fullKey(key), value, (err, stored) => {
        if (err || !stored) {
          // Mirror to localStorage so we don't lose state if Cloud is flaky.
          const ls = safeLocalStorage();
          if (ls) {
            try {
              ls.setItem(fullKey(key), value);
              resolve(true);
              return;
            } catch {
              // ignore
            }
          }
          resolve(false);
          return;
        }
        resolve(true);
      });
    });
  }
  const ls = safeLocalStorage();
  if (!ls) return false;
  try {
    ls.setItem(fullKey(key), value);
    return true;
  } catch {
    return false;
  }
}

export async function storageRemove(key: string): Promise<boolean> {
  const cloud = getCloudStorage();
  if (cloud) {
    return new Promise((resolve) => {
      cloud.removeItem(fullKey(key), (err, removed) => {
        if (err) {
          const ls = safeLocalStorage();
          ls?.removeItem(fullKey(key));
          resolve(false);
          return;
        }
        resolve(removed);
      });
    });
  }
  const ls = safeLocalStorage();
  if (!ls) return false;
  ls.removeItem(fullKey(key));
  return true;
}

// Convenience helpers for the small set of keys we actually use. Keep
// the list short — every key counts toward Telegram's per-bot quota.
export const StorageKeys = {
  lastHorizon: "last_horizon",
  lastCategory: "last_category",
} as const;
