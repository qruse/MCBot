"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { Session } from "../../paper/types";
import { apiBase, apiHeaders, useConnectionKey } from "../../backend/connection";

export type Settings = { market: "KR" | "US" | "GLOBAL"; capital: string; source: "toss" | "demo"; mode: "observer" | "adaptive" };
export type ServerSession = Session & {
  source: Settings["source"]; mode: Settings["mode"]; entriesPaused: boolean; entryBlock: string;
  continuousPaper?: boolean;
  policyVersion: number; leaseUntil: number | null;
  portfolioStatus?: null | {
    mode: "adaptive" | "allocation";
    rows: { symbol: string; theme: string | null; standing: boolean; retiring: boolean; targetPercent: number; actualPercent: number | null; actualAmount: number | null; targetAmount: number | null }[];
    nav: number | null; driftPercent: number; minimumTradeKrw: number; maxTurnoverPercent: number;
    lastRebalancedAt: number | null; nextRebalanceAt: number; reason: string;
  };
  pending?: null | { theme: string; at: number; version: number; weights?: Record<string, string> }
    | { kind: "portfolio"; at: number; version: number };
  strategyDecision?: null | { ref: string; timestamp: number; entry_group: string | null; rotate: boolean; reason: string };
  policy: null | { proposal_id: string; playbook_id: string; strategy_version?: number; strategy_name?: string; strategy_digest?: string; expires_at: number; rationale: string; hypothesis: string; counterevidence: string; allowed_symbols: string[]; evidence?: Evidence[] };
};
type Evidence = { evidence_id: string; source_url: string; publisher: string; published_at: number; retrieved_at?: number; claim: string; uncertainty?: string };
export type Research = {
  providerStatus?: null | { state: string; retry_after_seconds: number | null; last_failure: null | { reason: string; http_status: number | null; at: number; endpoint?: string } };
  strategies?: { ref: string; strategy_id: string; version: number; parent_ref: string; name: string; digest: string; status: string; hypothesis: string; failure_criterion: string }[];
  strategyFeedback?: { strategy_ref: string; source: string; closed_trades: number; realized_net: number; winning_trades: number; sessions: number }[];
  strategyEvaluations?: { id: string; kind: string; strategy_ref: string; created_at: number; passed?: boolean; input_count?: number; cases?: { case: string; passed: boolean; reason?: string }[]; results?: { strategy_ref: string; profit: number | null; fills: number; errors: number }[] }[];
  lastRun: null | { started: number; completed: number | null; deadline: number };
  nextReviewDue: number | null; trialCount: number; paired: boolean; difference: number | null;
  benchmark: null | { profit: number; timestamp: number; returnPercent: number };
  receipts: { proposal_id: string; source: string; status: string; reason: string; timestamp: number; rationale: string; evidence: Evidence[] }[];
  experiments: { experiment_id: string; hypothesis: string; failure_criterion: string; status: string; independent_sessions: number; minimum_sessions: number; review_after: number }[];
  archives: { id: string; active: number }[]; engineError: string | null;
};
export type Snapshot = { session: ServerSession; research: Research };

const moneyKeys = new Set(["capital", "baseline", "cash", "price", "rate", "close", "changePercent", "entryPrice", "entryFx", "entryFee", "entryCost", "priceKrw", "fx", "fee", "gross", "netProfit", "equity", "profit", "returnPercent", "difference", "realized_net", "targetPercent", "actualPercent", "actualAmount", "targetAmount", "nav", "driftPercent", "minimumTradeKrw", "maxTurnoverPercent"]);
// Exact decimal strings cross the API boundary. Conversion is for display only.
moneyKeys.add("amount"); moneyKeys.add("cashKrw"); moneyKeys.add("nativePrice");
function displayValues(value: unknown, key = ""): unknown {
  if (typeof value === "string" && moneyKeys.has(key)) return Number(value);
  if (Array.isArray(value)) return value.map(item => displayValues(item));
  if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, displayValues(v, k)]));
  return value;
}

export async function paperRequest(path: string, body?: unknown): Promise<unknown> {
  const response = await fetch(`${apiBase()}/paper/${path}`, { cache: "no-store", signal: AbortSignal.timeout(10000),
    method: body ? "POST" : "GET", headers: { ...apiHeaders(), ...(body ? { "Content-Type": "application/json", "X-MCBot-Command": "local-paper" } : {}) },
    body: body ? JSON.stringify(body) : undefined });
  const result = await response.json();
  if (!response.ok) throw new Error(result.detail ?? "backend_unavailable");
  return displayValues(result);
}

export function useServerSession() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const connection = useConnectionKey();
  const refresh = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    try { setSnapshot(await paperRequest("snapshot") as Snapshot); setError(null); }
    catch (e) {
      const code = e instanceof Error ? e.message : "";
      setError(code === "remote_token_required" ? "백엔드 접속 토큰이 맞지 않습니다. 터널 실행 시 출력된 링크로 다시 열어 주세요."
        : code === "remote_access_disabled" ? "백엔드에 원격 접속 토큰이 설정되지 않았습니다. 터널 실행 스크립트로 백엔드를 시작해 주세요."
        : "서버에 연결할 수 없습니다. 마지막으로 받은 정보를 표시합니다.");
    }
    finally { inFlight.current = false; }
  }, []);
  // Restart polling immediately when the saved backend address or token changes.
  useEffect(() => {
    const initial = window.setTimeout(() => { void refresh(); }, 0);
    let count = 0;
    const timer = window.setInterval(() => { if (!document.hidden || ++count % 6 === 0) void refresh(); }, 5000);
    return () => { window.clearTimeout(initial); window.clearInterval(timer); };
  }, [refresh, connection]);
  async function command(action: string, settings?: Settings) {
    if (!snapshot || busy) return;
    setBusy(true);
    try {
      await paperRequest("commands", { command_id: crypto.randomUUID(), session_id: snapshot.session.id, expected_version: snapshot.session.version, action, ...(settings ? { settings } : {}) });
      await refresh();
    } catch (e) {
      const code = e instanceof Error ? e.message : "";
      setError(code === "version_conflict" ? "다른 화면에서 상태가 변경됐습니다. 새로고침 후 다시 시도해 주세요."
        : code === "positions_require_exit_before_new_session" ? "보유 종목이 남아 있습니다. 기존 세션의 청산이 끝난 뒤 새 세션을 만들 수 있습니다."
        : "요청을 적용하지 못했습니다. 현재 상태를 확인해 주세요.");
    } finally { setBusy(false); }
  }
  return { snapshot, error, busy, command, refresh };
}
