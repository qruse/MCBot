import { ArrowDownToLine, Activity } from "lucide-react";
import { useEffect, useState } from "react";
import type { Session } from "../../paper/types";
import { krw, percent, signed, time } from "../format";
import { eventMessage } from "../messages";
import styles from "../dashboard.module.css";

export function ProfitChart({ session }: { session: Session }) {
  const [metric, setMetric] = useState<"profit" | "return">("profit");
  const [hover, setHover] = useState<number | null>(null);
  const [compact, setCompact] = useState(false);
  useEffect(() => {
    const query = window.matchMedia("(max-width: 560px)");
    const update = () => setCompact(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  if (session.lifecycle !== "preparing" && session.lifecycle !== "running") return null;
  const width = compact ? 420 : 860;
  const right = width - 118;
  const startedAt = session.events.filter(event => event.code === "start" || event.code === "resume").at(-1)?.timestamp ?? 0;
  const points = session.samples.filter(point => point.segment === session.segment && point.timestamp >= startedAt);
  const latest = points.at(-1);
  const values = points.map(point => metric === "profit" ? point.profit : point.returnPercent);
  const low = Math.min(0, ...values);
  const high = Math.max(0, ...values);
  const margin = Math.max((high - low) * 0.15, metric === "profit" ? 100 : 0.001);
  const min = low - margin;
  const max = high + margin;
  const first = points[0]?.timestamp ?? 0;
  const last = latest?.timestamp ?? first;
  const x = (timestamp: number) => 24 + (timestamp - first) / Math.max(5_000, last - first) * (right - 24);
  const y = (value: number) => 30 + (max - value) / (max - min) * 215;
  const segments = new Map<number, number[]>();
  points.forEach((point, index) => segments.set(point.segment, [...(segments.get(point.segment) ?? []), index]));
  const displayed = hover !== null ? points[Math.min(hover, points.length - 1)] : latest;
  const chartEvents = session.events.filter(event => (["buy", "sell", "risk"].includes(event.kind) || event.code === "policy_accepted") && event.timestamp >= first && event.timestamp <= last).slice(-60);

  function exportCsv() {
    const csv = ["기록시각,시세식별자,구간,순평가자산(원),현금(원),보유종목수,손익(원),수익률(%),시세기준시각,환율기준시각", ...points.map(point =>
      `${new Date(point.timestamp).toISOString()},"${point.snapshotId.replaceAll('"', '""')}",${point.segment},${point.equity.toFixed(6)},${point.cash.toFixed(6)},${point.holdings},${point.profit.toFixed(6)},${point.returnPercent.toFixed(8)},${point.priceSourceTime ? new Date(point.priceSourceTime).toISOString() : ""},${point.fxSourceTime ? new Date(point.fxSourceTime).toISOString() : ""}`)].join("\n");
    const url = URL.createObjectURL(new Blob(["\uFEFF", csv], { type: "text/csv;charset=utf-8;" }));
    const anchor = document.createElement("a");
    anchor.href = url; anchor.download = "mcbot-paper-preview.csv"; anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  return <section className={styles.panel} aria-labelledby="profit-title" data-testid="performance-panel">
    <div className={styles.panelHead}><h2 id="profit-title">손익 추이</h2><div className={styles.metricTabs}>{(["profit", "return"] as const).map(value => <button key={value} className={metric === value ? styles.selected : ""} onClick={() => setMetric(value)}>{value === "profit" ? "원" : "%"}</button>)}</div></div>
    {latest ? <>
      <div className={styles.chartDetail}><strong className={displayed!.profit < 0 ? styles.loss : styles.gain}>{metric === "profit" ? signed(displayed!.profit) : percent(displayed!.returnPercent)}</strong><span>{time(displayed!.timestamp)} · {hover === null ? "최근 기록" : "선택 기록"}<small>시세 기준 {time(displayed!.priceSourceTime)}{displayed!.fxSourceTime ? ` / 환율 기준 ${time(displayed!.fxSourceTime)}` : ""}</small></span></div>
      <div className={styles.chart}><svg viewBox={`0 0 ${width} 310`} role="img" aria-label="모의매매 수익 그래프" data-testid="profit-chart">
        {[0, 1, 2, 3, 4].map(index => <g key={index}><line x1="24" x2={right} y1={30 + index * 53.75} y2={30 + index * 53.75} className={styles.gridLine} /><text x={right + 15} y={34 + index * 53.75} className={styles.axis}>{metric === "profit" ? krw(max - (max - min) * index / 4) : `${(max - (max - min) * index / 4).toFixed(3)}%`}</text></g>)}
        <line x1="24" x2={right} y1={y(0)} y2={y(0)} className={styles.zeroLine} />
        {[...segments.entries()].map(([segment, indexes]) => <g key={segment}><path data-testid="profit-segment" d={indexes.map((index, i) => `${i ? "L" : "M"} ${x(points[index].timestamp)} ${y(values[index])}`).join(" ")} className={styles.profitLine} style={{ stroke: latest && latest.profit < 0 ? "#fb8c8c" : undefined }} />{indexes.length === 1 && <circle cx={x(points[indexes[0]].timestamp)} cy={y(values[indexes[0]])} r="3" fill="#40dbb4" />}</g>)}
        {chartEvents.map(event => <g key={event.id}><circle cx={x(event.timestamp)} cy="260" r="4" fill={event.kind === "risk" ? "#ffbd7a" : event.kind === "buy" ? "#40dbb4" : "#8faaff"}><title>{time(event.timestamp)} · {eventMessage(event)}</title></circle></g>)}
        {points.map((point, index) => <rect key={`${point.timestamp}-${index}`} x={x(point.timestamp) - 6} y="25" width="12" height="225" fill="transparent" onMouseEnter={() => setHover(index)} onMouseLeave={() => setHover(null)}><title>{time(point.timestamp)} · {signed(point.profit)} · {percent(point.returnPercent)}</title></rect>)}
        <text x="24" y="292" className={styles.axis}>0:00 경과</text><text x={right} y="292" textAnchor="end" className={styles.axis}>{Math.floor((last - first) / 60_000)}:{String(Math.floor((last - first) / 1_000) % 60).padStart(2, "0")} 경과</text>
      </svg></div>
    </> : <div className={styles.emptyChart} data-testid="profit-empty"><Activity size={35} strokeWidth={1.3} /><h3>기록 대기</h3></div>}
    <div className={styles.panelFoot}><span data-testid="profit-samples">기록 {points.length}개</span><button disabled={!latest} onClick={exportCsv}><ArrowDownToLine size={13} />CSV 다운로드</button></div>
    {session.config.market === "US" && <p className={styles.disclosure}>원화 손익 · 환율 변동 포함</p>}
  </section>;
}
