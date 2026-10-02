import type { ServerSession } from "../hooks/useServerSession";
import { krw, time } from "../format";
import { instrumentNames } from "../messages";
import styles from "../dashboard.module.css";

export function PortfolioAllocation({ session }: { session: ServerSession }) {
  const allocation = session.portfolioStatus;
  if (!allocation) return null;
  const rows = [...allocation.rows].sort((a, b) => {
    const rank = (row: (typeof allocation.rows)[number]) => row.symbol === "CASH" ? 0 : row.standing ? 2 : 1;
    return rank(a) - rank(b);
  });
  return <section className={styles.panel} aria-labelledby="allocation-title">
    <div className={styles.panelHead}><h2 id="allocation-title">{allocation.mode === "adaptive" ? "종목 · 테마 비중" : "자산 배분"}</h2><span className={styles.subtle}>정시 점검 · 허용 차이 {allocation.driftPercent}%p</span></div>
    <div className={styles.tableWrap}><table><thead><tr><th>자산</th><th>목표</th><th>현재</th><th>보유 금액</th><th>목표 금액</th></tr></thead>
      <tbody>{rows.map(row => <tr key={row.symbol}>
        <td><strong>{row.symbol === "CASH" ? "현금" : instrumentNames[row.symbol.split(":").at(-1)!] ?? row.symbol}</strong>{allocation.mode === "adaptive" && row.symbol !== "CASH" && <div className={styles.subtle}>{row.symbol.startsWith("KR:") ? "국내 · " : row.symbol.startsWith("US:") ? "미국 · " : ""}{row.retiring ? "교체 중" : row.standing ? "인버스" : row.theme}</div>}</td>
        <td>{row.targetPercent.toFixed(2)}%</td><td>{row.actualPercent === null ? "—" : `${row.actualPercent.toFixed(2)}%`}</td>
        <td>{row.actualAmount === null ? "—" : krw(row.actualAmount)}</td><td>{row.targetAmount === null ? "—" : krw(row.targetAmount)}</td>
      </tr>)}</tbody></table></div>
    <div className={styles.panelHead}><span className={styles.subtle}>최근 조정 {time(allocation.lastRebalancedAt)}</span><span className={styles.subtle}>최소 주문 {krw(allocation.minimumTradeKrw)}</span></div>
  </section>;
}
