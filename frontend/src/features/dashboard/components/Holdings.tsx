import type { Session } from "../../paper/types";
import { instruments } from "../../paper/universe";
import { displayMark } from "../displayPricing";
import { historyIssue, quoteIssue } from "../../paper/validation";
import { krw, signed, time } from "../format";
import { instrumentNames, message } from "../messages";
import styles from "../dashboard.module.css";

export function Holdings({ session }: { session: Session }) {
  const input = session.latest;
  const now = session.evaluatedAt;
  return <section className={styles.panel} aria-labelledby="holdings-title">
    <div className={styles.panelHead}><h2 id="holdings-title">보유 종목 <span className={styles.subtle}>{new Set(session.positions.map(p => p.symbol)).size}</span></h2><span className={styles.subtle}>최근 시세 · {time(input?.observedAt)}</span></div>
    {session.positions.length ? <div className={styles.tableWrap}><table><thead><tr><th>종목</th><th>수량</th><th>매수 원가</th><th>최근 가격</th><th title="매도 수수료 반영">평가금액</th><th>미실현 손익</th><th>위험 점검</th></tr></thead><tbody>{session.positions.map(position => {
      const market = position.market ?? session.legacyMarket ?? "KR";
      const native = input?.market === "GLOBAL" ? input.markets?.[market] : input;
      const nativeInput = native && input?.market === "GLOBAL" ? { ...native, fx: input.fx } : native;
      const globalMark = session.globalStatus?.holdings.find(item => item.entryId === position.entryId);
      const presentation = nativeInput ? displayMark(position, nativeInput, now, { ...session.config, market }) : null;
      const value = input?.market === "GLOBAL" ? globalMark?.amount != null ? {
        liquidation: globalMark.amount, profit: globalMark.amount - position.entryCost,
        price: presentation ? nativeInput?.displayQuotes?.[position.symbol]?.price ?? nativeInput?.quotes[position.symbol]?.price : null,
        sourceTime: globalMark.sourceTime, delayed: globalMark.closed || presentation?.delayed,
      } : null : presentation;
      const issue = nativeInput ? quoteIssue(nativeInput!.quotes[position.symbol], nativeInput!, now) : "No snapshot";
      const maIssue = nativeInput ? historyIssue(nativeInput!.minute[position.symbol], "minute", nativeInput!, now) : "No history";
      const builtin = !position.strategyRef || position.strategyRef.startsWith("theme-top3-v1@");
      const riskStatus = globalMark?.closed ? "장 마감 · 평가 시세" : issue ? `손절 검사 불가 · ${message(issue)}` : session.lifecycle === "paused" ? "위험 검사 일시정지" : session.strategyError ? "전략 오류 · 공통 손절 점검 유지" : builtin && maIssue ? "손절 검사 가능 · 이동평균 데이터 대기" : "손절 점검 중";
      return <tr key={position.entryId ?? `${position.symbol}-${position.entrySourceTime}`}><td><strong>{instrumentNames[position.symbol] ?? position.name ?? instruments.find(item => item.symbol === position.symbol)?.name ?? position.symbol}</strong><small>{position.symbol}</small></td><td>{position.shares.toLocaleString("ko-KR")}주</td><td>{krw(position.entryCost)}</td><td>{value?.price != null ? session.config.market === "GLOBAL" && market === "US" ? `$${value.price.toFixed(2)}` : krw(value.price) : "—"}<small>{time(value?.sourceTime)}{value?.delayed ? " · 지연" : ""}</small></td><td>{value ? krw(value.liquidation) : "—"}</td><td className={value && value.profit < 0 ? styles.loss : styles.gain}>{value ? signed(value.profit) : "—"}</td><td><span className={issue ? styles.loss : styles.subtle}>{riskStatus}</span></td></tr>;
    })}</tbody></table></div> : <div className={styles.emptyTable}>보유 종목 없음</div>}
  </section>;
}
