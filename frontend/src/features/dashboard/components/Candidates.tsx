import { useState } from "react";
import type { Session } from "../../paper/types";
import { quoteIssue } from "../../paper/validation";
import { krw } from "../format";
import { instrumentNames, message } from "../messages";
import styles from "../dashboard.module.css";

export function Candidates({ session }: { session: Session }) {
  const [search, setSearch] = useState("");
  const groups = session.candidateGroups ?? [];
  const standing = session.standingGroups ?? [];
  const displayed = [...standing.map(group => ({ group, pinned: true })), ...groups.map(group => ({ group, pinned: false }))];
  const expired = !!session.candidateExpiresAt && session.candidateExpiresAt <= session.evaluatedAt;
  return <details className={styles.fold} data-testid="candidates">
    <summary>후보 종목 <span>일반 {groups.reduce((sum, group) => sum + group.candidates.length, 0)} · 인버스 {standing.reduce((sum, group) => sum + group.candidates.length, 0)}</span></summary>
    <div className={styles.candidateBody}>
      {!!groups.length && <input aria-label="종목 검색" placeholder="종목명 · 코드 검색" value={search} onChange={event => setSearch(event.target.value)} />}
      {displayed.map(({ group, pinned }) => {
        const matches = group.candidates.filter(item => pinned || (item.name + " " + (instrumentNames[item.symbol] ?? "") + " " + item.symbol).toLowerCase().includes(search.trim().toLowerCase()));
        if (!matches.length) return null;
        return <div className={styles.theme} key={group.group_id} data-testid={pinned ? "standing-inverse" : undefined}><h3>{pinned ? "상시 인버스" : "일반 후보"}</h3><div className={styles.candidateCards}>{matches.map(item => {
          const input = session.latest;
          const quote = input?.quotes[item.symbol];
          const valid = input && !quoteIssue(quote, input, session.evaluatedAt);
          const check = session.candidateChecks?.[item.symbol];
          const issue = check === undefined ? "instrument_unverified" : check;
          return <article key={item.symbol} data-testid={pinned ? "standing-candidate" : "agent-candidate"}><header><strong>{instrumentNames[item.symbol] ?? item.name}</strong><span>{item.symbol}</span></header><span className={styles.badge}>{!pinned && expired ? "제안 만료" : issue ? message(issue) : "준비 완료"}</span>{pinned ? item.source_urls?.map(url => <small key={url}><a href={url} target="_blank" rel="noopener noreferrer">상품 정보 ↗</a></small>) : <details className={styles.inlineDetails}><summary>선정 근거</summary><p>{item.rationale}</p><small>{item.evidence_ids.join(", ")}</small></details>}<strong>{valid ? quote!.currency === "USD" ? "$" + quote!.price!.toFixed(2) : krw(quote!.price!) : "시세 대기"}</strong></article>;
        })}</div></div>;
      })}
      {!groups.length && <div className={styles.emptyTable}>일반 후보 없음</div>}
    </div>
  </details>;
}
