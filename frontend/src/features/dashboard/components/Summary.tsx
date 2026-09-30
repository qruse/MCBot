import type { Session } from "../../paper/types";
import { krw, signed, time } from "../format";
import styles from "../dashboard.module.css";

export function Summary({ session }: { session: Session }) {
  const sample = session.samples.at(-1);
  return <section className={styles.summary} aria-label="모의매매 요약">
    <div className={`${styles.stat} ${styles.profitStat}`}><span>누적 손익</span>
      <strong data-testid="session-profit" className={sample && sample.profit < 0 ? styles.loss : styles.gain}>{sample ? signed(sample.profit) : "—"}</strong>
      {sample && <small>{sample.returnPercent > 0 ? "+" : ""}{sample.returnPercent.toFixed(2)}% · {time(sample.timestamp)}</small>}</div>
    <div className={styles.stat}><span>총 자산</span><strong data-testid="session-equity">{krw(sample?.equity ?? session.config.capital)}</strong></div>
    <div className={styles.stat}><span>현금</span><strong data-testid="session-cash">{krw(sample?.cash ?? session.config.capital)}</strong></div>
    <div className={styles.stat}><span>보유 종목</span><strong data-testid="holding-count">{sample?.holdings ?? 0}<em>종목</em></strong></div>
  </section>;
}
