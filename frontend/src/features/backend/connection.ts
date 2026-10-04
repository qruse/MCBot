"use client";

import { useSyncExternalStore } from "react";

/** Backend address and remote token, kept in this browser so a changing tunnel URL needs no rebuild. */
export type BackendConnection = { url: string; token: string };

const STORAGE_KEY = "mcbot.backend";
const CHANGE_EVENT = "mcbot:backend";
const EMPTY = JSON.stringify({ url: "", token: "" });

const normalize = (url: string) => url.trim().replace(/\/+$/, "");

function defaultBase() {
  return normalize(process.env.NEXT_PUBLIC_API_BASE_URL ?? (typeof window !== "undefined"
    && ["3000", "3001"].includes(window.location.port) ? "http://127.0.0.1:8000" : "/api"));
}

function raw() {
  return typeof window === "undefined" ? EMPTY : window.localStorage.getItem(STORAGE_KEY) ?? EMPTY;
}

export function readConnection(): BackendConnection {
  try {
    const stored = JSON.parse(raw()) as Partial<BackendConnection>;
    return { url: stored.url ?? "", token: stored.token ?? "" };
  } catch {
    return { url: "", token: "" };
  }
}

export function saveConnection(next: BackendConnection) {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ url: normalize(next.url), token: next.token.trim() }));
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

export const apiBase = () => readConnection().url || defaultBase();

export function apiHeaders(): Record<string, string> {
  const { token } = readConnection();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** Reads `#api=...&token=...` from a tunnel link once. The fragment never reaches the web host. */
export function importConnectionFromHash() {
  const params = new URLSearchParams(window.location.hash.slice(1));
  const url = params.get("api");
  if (!url) return;
  saveConnection({ url, token: params.get("token") ?? "" });
  window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}`);
}

function subscribe(onChange: () => void) {
  window.addEventListener("storage", onChange);
  window.addEventListener(CHANGE_EVENT, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(CHANGE_EVENT, onChange);
  };
}

/** Re-renders when the saved connection changes, including from another tab. */
export function useConnectionKey() {
  return useSyncExternalStore(subscribe, raw, () => EMPTY);
}
