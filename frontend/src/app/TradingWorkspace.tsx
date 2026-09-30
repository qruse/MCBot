"use client";

import Link from "next/link";
import { Summary } from "../features/dashboard/components/Summary";
import { ProfitChart } from "../features/dashboard/components/ProfitChart";
import { Holdings } from "../features/dashboard/components/Holdings";
import { Readiness } from "../features/dashboard/components/Readiness";
import { Activity } from "../features/dashboard/components/Activity";
import { Candidates } from "../features/dashboard/components/Candidates";
import { StrategyLibrary } from "../features/dashboard/components/StrategyLibrary";
import { useServerSession } from "../features/dashboard/hooks/useServerSession";
import { StrategyPanel, ServerControls, ImprovementPanel, ResearchActivity } from "../features/dashboard/components/ResearchPanels";
import { time } from "../features/dashboard/format";
import styles from "../features/dashboard/dashboard.module.css";

export default function TradingWorkspace() {
  const paper = useServerSession();
  const session = paper.snapshot?.session;
  if (!session || !paper.snapshot) return <main className={styles.shell}><header className={styles.header}><strong>MCBot · 전략 운용 대시보드</strong></header><div className={styles.emptyChart}><h2>{paper.error ?? "서버 모의매매 기록을 불러오는 중입니다."}</h2><button className={styles.secondary} onClick={paper.refresh}>다시 연결</button></div></main>;
  const research = paper.snapshot.research;
  return <main className={styles.shell}>
    <header className={styles.header}>
      <Link className={styles.brand} href="/" aria-label="MCBot 홈"><span>MC</span><strong>MCBot</strong></Link>
      <div className={styles.headerStatus}><span className={`${styles.badge} ${session.source === "demo" ? styles.waiting : ""}`}>{session.source === "toss" ? "모의매매 · 실제 시세" : "데모 · 가상 시세"}</span><span>{session.config.market === "KR" ? "국내" : "미국"}</span><time>갱신 {time(session.evaluatedAt)}</time></div>
    </header>
    <h1 className={styles.visuallyHidden}>운용 현황</h1>
    {paper.error && <p role="alert" className={styles.warning}>{paper.error}</p>}
    <Summary session={session} />
    <div className={styles.workspace}>
      <aside className={styles.controls}>
        <ServerControls key={session.id} session={session} busy={paper.busy} command={paper.command} />
        <StrategyPanel session={session} research={research} />
        <details className={styles.fold}><summary>데이터 준비 <span>{session.ready}/{session.total}</span></summary><Readiness session={session} source={session.source} /></details>
      </aside>
      <div className={styles.mainColumn}><ProfitChart session={session} /><Holdings session={session} /><Activity session={session} /></div>
    </div>
    <div className={styles.detailsStack}>
      <Candidates session={session} />
      <details className={styles.fold}><summary>전략 · 연구 기록 <span>{research.strategies?.length ?? 0}개 버전</span></summary><div className={styles.researchGrid}><ImprovementPanel session={session} research={research} /><StrategyLibrary session={session} research={research} /><ResearchActivity research={research} /></div></details>
    </div>
  </main>;
}
