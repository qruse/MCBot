import type { Session } from "../../paper/types";
import { krw, signed, time } from "../format";
import { displayValuation } from "../displayPricing";
import styles from "../dashboard.module.css";

export function Summary({ session }: { session: Session }) {
  const sample = session.samples.at(-1);
  const global = session.globalStatus;
  const local = session.config.market === "GLOBAL" ? null : displayValuation(session);
  const value = global?.equity != null ? { equity: global.equity,
    sourceTime: global.holdings.length ? Math.min(...global.holdings.map(h => h.sourceTime ?? session.evaluatedAt)) : null,
    delayed: global.holdings.some(h => h.closed), } : local;
  const profit = value && session.baseline !== null ? value.equity - session.baseline : sample?.profit;
  const percent = profit !== undefined && session.baseline ? profit / session.baseline * 100 : sample?.returnPercent;
  const equity = value?.equity ?? sample?.equity ?? (session.positions.length ? null : session.cash);
  return <section className={styles.summary} aria-label="모의매매 요약">
    <div className={`${styles.stat} ${styles.profitStat}`}><span>누적 손익</span>
      <strong data-testid="session-profit" className={profit !== undefined && profit < 0 ? styles.loss : styles.gain}>{profit !== undefined ? signed(profit) : "—"}</strong>
      {percent !== undefined && <small>{percent > 0 ? "+" : ""}{percent.toFixed(2)}% · {value ? `${value.delayed ? "지연 가격" : "가격"} ${time(value.sourceTime)}` : `최근 기록 ${time(sample?.timestamp)}`}</small>}</div>
    <div className={styles.stat}><span>총 자산</span><strong data-testid="session-equity">{equity === null ? "—" : krw(equity)}</strong></div>
    <div className={styles.stat}><span>현금</span><strong data-testid="session-cash">{krw(global?.cashKrw ?? session.cash)}</strong></div>
    <div className={styles.stat}><span>보유 종목</span><strong data-testid="holding-count">{new Set(session.positions.map(p => `${p.market ?? session.config.market}:${p.symbol}`)).size}<em>종목</em></strong></div>
  </section>;
}
