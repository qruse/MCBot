import type { Session } from "../../paper/types";
import { instruments } from "../../paper/universe";
import { mark } from "../../paper/accounting";
import { historyIssue, quoteIssue } from "../../paper/validation";
import { krw, signed, time } from "../format";
import { instrumentNames, message } from "../messages";
import styles from "../dashboard.module.css";

export function Holdings({ session }: { session: Session }) {
  const input = session.latest;
  const now = session.evaluatedAt;
  return <section className={styles.panel} aria-labelledby="holdings-title">
    <div className={styles.panelHead}><h2 id="holdings-title">보유 종목 <span className={styles.subtle}>{session.positions.length}</span></h2><span className={styles.subtle}>최근 시세 · {time(input?.observedAt)}</span></div>
    {session.positions.length ? <div className={styles.tableWrap}><table><thead><tr><th>종목</th><th>수량</th><th>매수 원가</th><th>예상 청산금액</th><th>미실현 손익</th><th>위험 점검</th></tr></thead><tbody>{session.positions.map(position => {
      const value = input ? mark(position, input, now, session.config) : null;
      const issue = input ? quoteIssue(input.quotes[position.symbol], input, now) : "No snapshot";
      const maIssue = input ? historyIssue(input.minute[position.symbol], "minute", input, now) : "No history";
      const builtin = !position.strategyRef || position.strategyRef.startsWith("theme-top3-v1@");
      const riskStatus = issue ? `손절 검사 불가 · ${message(issue)}` : session.lifecycle === "paused" ? "위험 검사 일시정지" : session.strategyError ? "전략 오류 · 공통 손절 점검 유지" : builtin && maIssue ? "손절 검사 가능 · 이동평균 데이터 대기" : "손절 점검 중";
      return <tr key={position.symbol}><td><strong>{instrumentNames[position.symbol] ?? position.name ?? instruments.find(item => item.symbol === position.symbol)?.name ?? position.symbol}</strong><small>{position.symbol}</small></td><td>{position.shares.toLocaleString("ko-KR")}주</td><td>{krw(position.entryCost)}</td><td>{value ? krw(value.liquidation) : "—"}</td><td className={value && value.profit < 0 ? styles.loss : styles.gain}>{value ? signed(value.profit) : "—"}</td><td><small>{time(input?.quotes[position.symbol]?.sourceTime)}</small><span className={issue ? styles.loss : styles.subtle}>{riskStatus}</span></td></tr>;
    })}</tbody></table></div> : <div className={styles.emptyTable}>보유 종목 없음</div>}
  </section>;
}
