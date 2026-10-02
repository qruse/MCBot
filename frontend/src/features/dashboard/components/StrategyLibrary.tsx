import type { Research, ServerSession } from "../hooks/useServerSession";
import { signed, time } from "../format";
import styles from "../dashboard.module.css";

const moduleName = (id: string, name: string) => id === "theme-top3-v1" ? "테마 추세" : id === "cash-v1" ? "신규 매수 보류" : id === "adaptive-allocation" ? "종목 · 테마 비중 조정" : id === "allocation-band" ? "자산 배분 · 비중 조정" : id === "patient-trend" ? "추세 · 자동 교체 없음" : id.startsWith("demo-roundtrip") ? "데모 매수·청산" : name;

export function StrategyLibrary({ session, research }: { session: ServerSession; research: Research }) {
  const active = session.policy ? `${session.policy.playbook_id}@${session.policy.strategy_version ?? 1}` : null;
  const modules = research.strategies ?? [];
  return <section className={styles.panel} aria-labelledby="strategy-library-title" data-testid="strategy-library">
    <div className={styles.panelHead}><h2 id="strategy-library-title">전략 모듈</h2><span className={styles.badge}>{modules.length}개 버전</span></div>
    <div className={styles.tableWrap}><table><thead><tr><th>전략 / 코드 버전</th><th>상태</th><th>청산 건수</th><th>실제 시세 모의 손익</th></tr></thead><tbody>{modules.map(item => {
      const feedback = research.strategyFeedback?.find(f => f.strategy_ref === item.ref && f.source === "toss");
      return <tr key={item.ref}><td><strong>{moduleName(item.strategy_id, item.name)} · v{item.version}</strong><small>{item.ref}</small></td><td>{active === item.ref ? "적용 중" : item.status === "builtin" ? "기본 모듈" : "모의 운용 가능"}</td><td>{feedback?.closed_trades ?? 0}</td><td>{feedback ? signed(feedback.realized_net) : "측정 전"}</td></tr>;
    })}</tbody></table></div>
    <p className={styles.disclosure}>손익은 해당 코드 버전으로 진입한 뒤 청산한 모의 거래의 합계입니다. 예시 데이터와 미실현 손익은 제외합니다.</p>
    <details className={styles.exchangeHelp}><summary>변경 근거 · 검증 기록</summary>
      {modules.filter(item => item.status !== "builtin").map(item => <article key={item.ref}><p><strong>{item.ref}</strong> · 이전 코드 {item.parent_ref}</p><p>{item.hypothesis}</p><p>실패 기준: {item.failure_criterion}</p><code>{item.digest}</code></article>)}
      {(research.strategyEvaluations ?? []).slice(0, 8).map(item => <article key={item.id}>
        <p><strong>{item.strategy_ref}</strong> · {time(item.created_at)} · {item.kind === "contract_checks" ? item.passed ? "동작 검증 통과" : "동작 검증 실패" : `기록 재생 ${item.input_count ?? 0}개 입력`}</p>
        {item.cases?.filter(c => !c.passed).map(c => <p key={c.case}>{c.case} · {c.reason}</p>)}
        {item.results?.map((result, i) => <p key={`${result.strategy_ref}-${i}`}>{result.strategy_ref} · 손익 {result.profit === null ? "평가 불가" : signed(result.profit)} · 체결 {result.fills}건 · 오류 {result.errors}건</p>)}
      </article>)}
      {!research.strategyEvaluations?.length && <p>검증 기록이 없습니다.</p>}
      <p>동작 검증은 코드 계약과 오류 처리를 확인합니다. 과거 기록 재생만으로 수익성을 검증하지 않습니다.</p>
    </details>
  </section>;
}
