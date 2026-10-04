"use client";

import { useEffect, useState } from "react";
import styles from "../dashboard/dashboard.module.css";
import { importConnectionFromHash, readConnection, saveConnection } from "./connection";

/** Header control for the backend address (e.g. a Cloudflare quick tunnel) and its remote token. */
export function BackendConnection({ connected, open = false }: { connected: boolean; open?: boolean }) {
  const [draft, setDraft] = useState<{ url: string; token: string } | null>(null);

  useEffect(() => { importConnectionFromHash(); }, []);

  return <details className={styles.backendConnection} open={open} onToggle={event => { if (event.currentTarget.open) setDraft(readConnection()); }}>
    <summary className={`${styles.badge} ${connected ? styles.ready : styles.waiting}`}>{connected ? "백엔드 연결됨" : "백엔드 연결 안 됨"}</summary>
    <form onSubmit={event => {
      event.preventDefault();
      if (draft) saveConnection(draft);
      event.currentTarget.closest("details")?.removeAttribute("open");
    }}>
      <label>백엔드 주소<input value={draft?.url ?? ""} placeholder="https://xxxx.trycloudflare.com" spellCheck={false}
        onChange={event => setDraft({ token: draft?.token ?? "", url: event.target.value })} /></label>
      <label>접속 토큰<input type="password" value={draft?.token ?? ""} placeholder="로컬 접속이면 비워 두세요" autoComplete="off"
        onChange={event => setDraft({ url: draft?.url ?? "", token: event.target.value })} /></label>
      <small>비워 두면 기본 주소로 접속합니다. 터널 실행 시 출력된 링크로 열면 자동으로 입력됩니다.</small>
      <button className={styles.secondary} type="submit">저장하고 다시 연결</button>
    </form>
  </details>;
}
