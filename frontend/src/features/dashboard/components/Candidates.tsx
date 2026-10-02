import { useState } from "react";
import type { ServerSession } from "../hooks/useServerSession";
import { quoteIssue } from "../../paper/validation";
import { krw, time } from "../format";
import { instrumentNames, message } from "../messages";
import styles from "../dashboard.module.css";

export function Candidates({ session }: { session: ServerSession }) {
  const [tab, setTab] = useState<"general" | "inverse">("general");
  const groups = session.candidateGroups ?? [];
  const standing = session.standingGroups ?? [];
  const expired = !!session.candidateExpiresAt && session.candidateExpiresAt <= session.evaluatedAt;
  const checks: Record<string, string> = { instrument_unverified: "종목 확인 대기", instrument_ineligible: "거래 대상 제외", candidate_quote_unavailable: "시세 대기", candidate_history_pending: "이력 수집 중", candidate_change_pending: "등락률 대기" };
  const sets = [{ groups, pinned: false, id: "general" }, { groups: standing, pinned: true, id: "inverse" }];
  return <section className={`${styles.panel} ${styles.strategyCandidates}`} data-testid="candidates" aria-labelledby="candidates-title">
    <div className={styles.panelHead}><h2 id="candidates-title">투자 후보</h2><div className={styles.candidateTabs}>
      <button type="button" aria-pressed={tab === "general"} onClick={() => setTab("general")}>개별주 {groups.reduce((sum, g) => sum + g.candidates.length, 0)}</button>
      <button type="button" aria-pressed={tab === "inverse"} onClick={() => setTab("inverse")}>지수 인버스 {standing.reduce((sum, g) => sum + g.candidates.length, 0)}</button>
    </div></div>
    {expired && tab === "general" && !!groups.length && <p className={styles.candidateExpiry}>개별주 검토 만료</p>}
    {sets.map(({ groups: rows, pinned, id }) => <div key={id} hidden={tab !== id} className={`${styles.tableWrap} ${styles.candidateTable}`}>
      {rows.length ? <table><thead><tr><th>종목</th><th>체결용 시세</th><th>데이터</th></tr></thead><tbody>{rows.flatMap(group => group.candidates.map(item => {
        const market = item.market ?? session.legacyMarket ?? "KR";
        const global = session.config.market === "GLOBAL";
        const instrumentKey = global ? `${market}:${item.symbol}` : item.symbol;
        const native = global ? session.latest?.markets?.[market] : session.latest;
        const input = global && native ? { ...native, fx: session.latest?.fx ?? null } : native;
        const quote = input?.quotes[item.symbol];
        const valid = !!input && (!global || input.marketOpen) && !quoteIssue(quote, input, session.evaluatedAt);
        const check = session.candidateChecks?.[instrumentKey];
        const issue = check === undefined ? "종목 확인 대기" : check ? checks[check] ?? message(check) : !valid ? "시세 대기" : "준비 완료";
        const sources = session.policy?.evidence?.filter(e => item.evidence_ids.includes(e.evidence_id)) ?? [];
        const shares = session.positions.filter(p => p.symbol === item.symbol && (!global || p.market === market)).reduce((sum, p) => sum + p.shares, 0);
        return <tr key={instrumentKey} data-testid={pinned ? "standing-candidate" : "agent-candidate"}>
          <td><strong>{instrumentNames[item.symbol] ?? item.name}</strong><small>{global ? `${market === "KR" ? "국내" : "미국"} · ` : ""}{item.symbol}{shares ? ` · ${shares}주 보유` : " · 미보유"}</small>
            <details className={styles.candidateEvidence}><summary>{pinned ? "상품 정보" : "선정 근거"}</summary>
              {!pinned && <p>{item.rationale}</p>}
              {sources.map(e => <a key={e.evidence_id} href={e.source_url} target="_blank" rel="noopener noreferrer">{e.publisher} ↗</a>)}
              {pinned && item.source_urls?.map(url => <a key={url} href={url} target="_blank" rel="noopener noreferrer">상품 정보 ↗</a>)}
            </details>
          </td>
          <td>{valid ? quote!.currency === "USD" ? `$${quote!.price!.toFixed(2)}` : krw(quote!.price!) : "—"}<small>{valid ? time(quote!.sourceTime) : "유효한 가격 없음"}</small></td>
          <td><span className={`${styles.badge} ${issue !== "준비 완료" ? styles.waiting : styles.ready}`}>{issue}</span></td>
        </tr>;
      }))}</tbody></table> : <p className={styles.emptyTable}>{pinned ? "인버스 후보 없음" : "개별주 후보 없음"}</p>}
    </div>)}
  </section>;
}
