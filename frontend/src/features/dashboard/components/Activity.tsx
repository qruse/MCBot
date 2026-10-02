import { useState } from "react";
import type { Session } from "../../paper/types";
import { krw, signed, label, time } from "../format";
import { eventMessage, instrumentNames } from "../messages";
import styles from "../dashboard.module.css";

export function Activity({ session }: { session: Session }) {
  const [filter, setFilter] = useState("fills");
  const events = session.events.filter(event => filter === "all" || ["risk", "data", "decision"].includes(event.kind)).slice().reverse();
  const fills = session.fills.slice().reverse();
  return <section className={styles.panel} aria-labelledby="activity-title">
    <div className={styles.panelHead}><h2 id="activity-title">최근 거래</h2><select aria-label="기록 필터" value={filter} onChange={event => setFilter(event.target.value)}><option value="fills">체결</option><option value="all">전체 기록</option><option value="risk">위험·데이터</option></select></div>
    {filter === "fills" ? fills.length ? <div className={styles.tableWrap}><table><thead><tr><th>시각</th><th>거래</th><th>종목</th><th>수량</th><th>체결가</th><th>수수료</th><th>확정 손익</th></tr></thead><tbody>{fills.slice(0, 12).map(fill => <tr key={fill.id}><td>{time(fill.timestamp)}</td><td><span className={fill.side === "buy" ? styles.gain : styles.loss}>{fill.side === "buy" ? "매수" : "매도"}</span></td><td>{instrumentNames[fill.symbol] ?? fill.symbol}</td><td>{fill.shares}주</td><td>{fill.currency === "USD" && fill.nativePrice != null ? <><strong>${fill.nativePrice.toFixed(2)}</strong><small>{krw(fill.priceKrw)}</small></> : krw(fill.priceKrw)}</td><td>{krw(fill.fee)}</td><td className={fill.netProfit !== null && fill.netProfit < 0 ? styles.loss : styles.gain}>{fill.netProfit === null ? "—" : signed(fill.netProfit)}</td></tr>)}</tbody></table></div> : <div className={styles.emptyTable}>체결 없음</div>
      : events.length ? <ol className={styles.events}>{events.slice(0, 30).map(event => <li key={event.id}><time>{time(event.timestamp)}</time><span className={styles.eventTag}>{label(event.kind)}</span><p>{eventMessage(event)}</p></li>)}</ol> : <div className={styles.emptyTable}>기록 없음</div>}
  </section>;
}
