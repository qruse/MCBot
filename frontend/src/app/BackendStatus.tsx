"use client";

import { useEffect, useState, useSyncExternalStore } from "react";

import styles from "./page.module.css";

type Language = "en" | "ko";
type Health = { url: string; online: boolean };

const STORAGE_KEY = "mcbot.backendUrl";
const CHANGE_EVENT = "mcbot:backend-url";
const DEFAULT_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";
const POLL_MS = 15_000;
const TIMEOUT_MS = 5_000;

const copy = {
  en: {
    title: "Backend",
    online: "Connected",
    offline: "Disconnected",
    checking: "Checking...",
    placeholder: "https://xxxx.trycloudflare.com",
    save: "Connect",
  },
  ko: {
    title: "백엔드",
    online: "연결됨",
    offline: "연결 안 됨",
    checking: "확인 중...",
    placeholder: "https://xxxx.trycloudflare.com",
    save: "연결",
  },
} as const;

function normalizeUrl(url: string) {
  return url.trim().replace(/\/+$/, "");
}

function storeUrl(url: string) {
  window.localStorage.setItem(STORAGE_KEY, normalizeUrl(url));
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

function subscribe(onChange: () => void) {
  window.addEventListener("storage", onChange);
  window.addEventListener(CHANGE_EVENT, onChange);

  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(CHANGE_EVENT, onChange);
  };
}

function readUrl() {
  return window.localStorage.getItem(STORAGE_KEY) || DEFAULT_URL;
}

async function isHealthy(url: string) {
  try {
    const response = await fetch(`${url}/health`, {
      cache: "no-store",
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
    const body = (await response.json()) as { status?: string };

    return response.ok && body.status === "ok";
  } catch {
    return false;
  }
}

export default function BackendStatus({ language }: { language: Language }) {
  const t = copy[language];
  const url = useSyncExternalStore(subscribe, readUrl, () => DEFAULT_URL);
  const [draft, setDraft] = useState<string | null>(null);
  const [health, setHealth] = useState<Health | null>(null);

  // A tunnel link like /?api=https://xxxx.trycloudflare.com saves the backend URL once.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const api = params.get("api");

    if (api) {
      storeUrl(api);
      params.delete("api");
      const query = params.toString();
      window.history.replaceState(null, "", `${window.location.pathname}${query ? `?${query}` : ""}`);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function check() {
      const online = await isHealthy(url);

      if (!cancelled) {
        setHealth({ url, online });
      }
    }

    check();
    const timer = window.setInterval(check, POLL_MS);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [url]);

  const status = health?.url !== url ? "checking" : health.online ? "online" : "offline";

  return (
    <form
      className={styles.backendBox}
      onSubmit={(event) => {
        event.preventDefault();

        if (draft !== null && normalizeUrl(draft)) {
          storeUrl(draft);
        }

        setDraft(null);
      }}
    >
      <span>{t.title}</span>
      <strong className={styles[`backend_${status}`]}>
        <i aria-hidden="true" />
        {t[status]}
      </strong>
      <input
        aria-label={t.title}
        value={draft ?? url}
        onChange={(event) => setDraft(event.target.value)}
        placeholder={t.placeholder}
        spellCheck={false}
      />
      <button type="submit">{t.save}</button>
    </form>
  );
}
