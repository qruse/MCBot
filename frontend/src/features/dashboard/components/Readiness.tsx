import { Check, Clock3 } from "lucide-react";
import type { Session } from "../../paper/types";
import { time } from "../format";
import { message } from "../messages";
import styles from "../dashboard.module.css";

export function Readiness({ session, source }: { session: Session; source: "toss" | "demo" }) {
  const input = session.latest;
  const now = session.evaluatedAt;
  const standing = new Set((session.standingGroups ?? []).flatMap(group => group.candidates.map(item => item.symbol)));
  const candidates = [...(session.standingGroups ?? []), ...(session.candidateGroups ?? [])].flatMap(group => group.candidates);
  const receivedAt = input ? Math.max(0, ...Object.values(input.quotes).map(quote => quote?.receivedAt ?? 0)) : 0;
  return <section className={styles.panel} aria-labelledby="readiness-title">
    <div className={styles.panelHead}><div><span className={styles.eyebrow}>매매 준비</span><h2 id="readiness-title">전략 준비 상태</h2></div><strong data-testid="strategy-progress">{session.ready}/{session.total}</strong></div>
    <div className={styles.readinessBody}><progress max={session.total || 1} value={session.ready} aria-label="전략 데이터 준비 현황" />
      {!session.candidateGroups?.length && <p>일반 후보는 Codex의 종목 선정을 기다립니다.</p>}
      <ul className={styles.readinessList}>{candidates.map(item => {
        const check = session.candidateChecks?.[item.symbol];
        const issue = check === undefined ? "instrument_unverified" : check;
        const status = issue ? message(issue) : "준비 완료";
        return <li key={item.symbol}><span>{issue ? <Clock3 size={12} /> : <Check size={12} />}{item.symbol}{standing.has(item.symbol) ? " · 상시" : ""}</span><span title={status}>{!standing.has(item.symbol) && session.candidateExpiresAt && session.candidateExpiresAt <= now ? "후보 제안 만료" : status}</span></li>;
      })}</ul><div className={styles.metadata}><span>{source === "toss" ? "실제 시세 갱신" : "예시 시세 갱신"}<strong>30초마다</strong></span><span>수익 기록<strong>5초마다</strong></span><span>마지막 시세 수신<strong>{time(receivedAt || null)}</strong></span></div>
    </div>
  </section>;
}
