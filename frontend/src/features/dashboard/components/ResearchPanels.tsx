"use client";

import { useState } from "react";
import type { Research, ServerSession, Settings, Snapshot } from "../hooks/useServerSession";
import { paperRequest } from "../hooks/useServerSession";
import { krw, signed, time, label } from "../format";
import { message } from "../messages";
import { Summary } from "./Summary";
import styles from "../dashboard.module.css";

const playbook = (id?: string, name?: string) => id?.startsWith("demo-roundtrip") ? "데모 매수·청산" : id === "theme-top3-v1" ? "테마 추세" : id === "cash-v1" ? "현금 대기" : name ?? "전략 없음";
const blocks: Record<string, string> = { observer: "관찰 모드", awaiting_review: "전략 검토 대기", policy_expired: "전략 만료 · 신규 매수 중지", cash_policy: "현금 유지", entries_paused: "신규 매수 중지", none: "진입 조건 확인 중" };
const receiptLabels: Record<string, string> = { accepted: "적용", observed: "관찰", rejected: "거절" };

export function StrategyPanel({ session: s, research: r }: { session: ServerSession; research: Research }) {
  const demoComplete = s.source === "demo" && s.policy?.playbook_id.startsWith("demo-roundtrip") && !s.positions.length && s.fills.some(fill => fill.side === "sell");
  const late = r.lastRun && !r.lastRun.completed && s.evaluatedAt > r.lastRun.deadline;
  return <section className={styles.panel} aria-labelledby="strategy-title">
    <div className={styles.panelHead}><h2 id="strategy-title">현재 전략</h2>{s.policy && <span className={styles.badge}>v{s.policy.strategy_version ?? 1}</span>}</div>
    <div className={styles.strategyBrief}><strong>{playbook(s.policy?.playbook_id, s.policy?.strategy_name)}</strong>
      <dl><div><dt>최근 검토</dt><dd>{time(r.lastRun?.completed ?? r.lastRun?.started)}</dd></div><div><dt>{demoComplete ? "데모 상태" : "유효 기한"}</dt><dd>{demoComplete ? "완료" : time(s.policy?.expires_at)}</dd></div><div><dt>다음 검토 기준</dt><dd>{time(r.nextReviewDue)}</dd></div></dl>
      {s.policy && <details className={styles.inlineDetails}><summary>선택 근거</summary><p>{s.policy.rationale}</p></details>}
    </div>
    {late && <p className={styles.warning}>전략 검토 지연</p>}
  </section>;
}

export function ServerControls({ session: s, busy, command }: { session: ServerSession; busy: boolean; command: (action: string, settings?: Settings) => Promise<void> }) {
  const [settings, setSettings] = useState<Settings>({ market: s.config.market, capital: String(s.config.capital), source: s.source, mode: s.mode });
  const [confirm, setConfirm] = useState(false);
  const active = ["running", "preparing"].includes(s.lifecycle);
  const idle = s.lifecycle === "idle";
  const demoComplete = s.source === "demo" && s.policy?.playbook_id.startsWith("demo-roundtrip") && !s.positions.length && s.fills.some(fill => fill.side === "sell");
  const valid = Number(settings.capital) >= 1000000 && Number(settings.capital) <= 1e12;
  const dirty = settings.market !== s.config.market || settings.source !== s.source || settings.mode !== s.mode || Number(settings.capital) !== s.config.capital;
  return <section className={styles.panel} data-testid="session-controls"><div className={styles.panelHead}><h2>운용 상태</h2><span className={`${styles.badge} ${active ? styles.ready : ""}`} data-testid="session-lifecycle">{label(s.lifecycle)}</span></div>
    <div className={styles.controlBody}>
      <div className={styles.operationState}><strong>{s.strategyError ? "전략 오류" : s.lifecycle === "halted" ? "위험 한도 도달" : s.lifecycle === "paused" ? "운용 정지" : idle ? "시작 전" : demoComplete ? "데모 완료" : s.positions.length ? `${s.positions.length}종목 보유` : "현금 대기"}</strong><span>{s.lifecycle === "paused" ? "매매·위험 점검 중지" : s.strategyError ? "신규 매수 중지 · 손절 점검 유지" : demoComplete ? "매수·청산 완료 · 현금 유지" : s.entryBlock !== "none" ? blocks[s.entryBlock] ?? message(s.entryBlock) : s.condition !== "ready" ? message(s.reason) : "진입 조건 확인 중"}</span></div>
      <details className={styles.settingsFold} open={idle}><summary>설정 <span>{s.config.market === "KR" ? "국내" : "미국"} · {krw(s.config.capital)}</span></summary>
      <label className={styles.field}><span>시세 데이터</span><select aria-label="시세 데이터" disabled={!idle || busy} value={settings.source} onChange={e => setSettings({ ...settings, source: e.target.value as Settings["source"] })}><option value="toss">토스증권 실제 시세 · 모의매매</option><option value="demo">예시 데이터 · 검증 전용</option></select></label>
      <label className={styles.field}><span>운용 방식</span><select aria-label="운용 방식" disabled={!idle || busy} value={settings.mode} onChange={e => setSettings({ ...settings, mode: e.target.value as Settings["mode"] })}><option value="observer">연구 관찰 · 제안 기록만</option><option value="adaptive">검증된 제안으로 모의매매</option></select></label>
      <label className={styles.field}><span>거래 시장</span><select aria-label="거래 시장" disabled={!idle || busy} value={settings.market} onChange={e => setSettings({ ...settings, market: e.target.value as Settings["market"] })}><option value="KR">국내 주식</option><option value="US">미국 주식</option></select></label>
      <label className={styles.field}><span>시작 자금 · 원화</span><input aria-label="시작 자금" type="number" min="1000000" max="1000000000000" disabled={!idle || busy} value={settings.capital} onChange={e => setSettings({ ...settings, capital: e.target.value })} /></label>
      </details>
      {dirty && idle ? <button className={styles.primary} disabled={busy || !valid} onClick={() => command("new", settings)}>설정 저장</button> : <button className={styles.primary} disabled={busy || s.lifecycle === "halted"} onClick={() => command(active ? "pause" : idle ? "start" : "resume")}>{busy ? "적용 중…" : active ? "시뮬레이션 정지" : idle ? "모의매매 시작" : "모의매매 재개"}</button>}
      {active && s.mode === "adaptive" && <button className={styles.secondary} style={{ marginTop: 10 }} disabled={busy} onClick={() => command(s.entriesPaused ? "resume_entries" : "pause_entries")}>{s.entriesPaused ? "신규 매수 허용" : "신규 매수 중지"}</button>}
      <div className={styles.riskStrip}><span>손절 <b>2%</b></span><span>전체 손실 중단 <b>5%</b></span></div>
      <details className={styles.inlineDetails}><summary>운용 · 비용 기준</summary><p>창을 닫아도 실행 · 서버 재시작 시 정지</p><p>정지하면 위험 점검도 중지됩니다.</p><p>장 마감 5분 전 청산</p><p>{s.config.market === "KR" ? "KRX 수수료 매수·매도 각각 0.015%" : "수수료 매수·매도 각각 0.1%"}</p><p>세금·슬리피지 등 기타 비용 미반영</p></details>
      <div className={styles.resetArea}>{confirm ? <div className={styles.confirm}><p>기존 기록을 보관하고 새 세션을 만들까요?</p><button disabled={busy} onClick={async () => { await command("new", settings); setConfirm(false); }}>보관 후 새 세션</button><button onClick={() => setConfirm(false)}>취소</button></div> : <button className={styles.secondary} disabled={busy || active || idle || !!s.positions.length} onClick={() => setConfirm(true)}>기록 보관 · 새 세션</button>}</div>
    </div>
  </section>;
}

export function ImprovementPanel({ session: s, research: r }: { session: ServerSession; research: Research }) {
  const latest = s.samples.at(-1);
  return <section className={styles.panel} aria-labelledby="improvement-title"><div className={styles.panelHead}><h2 id="improvement-title">성과 비교</h2><span className={styles.badge}>등록 실험 {r.trialCount}</span></div>
    <div className={styles.tableWrap}><table><thead><tr><th>비교 대상</th><th>수수료 반영 손익</th><th>기준</th></tr></thead><tbody>
      <tr><td>현재 운용</td><td>{latest ? signed(latest.profit) : "기록 대기"}</td><td>{s.mode === "observer" ? "관찰 · 현금" : "Codex 전략 선택"}</td></tr>
      <tr><td>고정 기준 전략</td><td>{r.benchmark ? signed(r.benchmark.profit) : "기록 대기"}</td><td>고정 후보 · 같은 시세·자금·수수료·위험 규칙</td></tr>
      <tr><td>기준 대비 차이</td><td>{r.paired && r.difference !== null ? signed(r.difference) : "동시점 기록 대기"}</td><td>{r.paired ? time(r.benchmark?.timestamp) : "동일 시각의 평가만 비교"}</td></tr>
      <tr><td>현금 유지</td><td>{latest ? krw(0) : "기록 대기"}</td><td>시작 자금 유지 · 이자 미반영</td></tr>
    </tbody></table></div>
    <p className={styles.disclosure}>수수료 반영 · 세금·슬리피지 등 기타 비용 제외</p>
    <div className={styles.hypotheses}>{r.experiments.length ? r.experiments.slice(0, 5).map(e => <article key={e.experiment_id}><span className={styles.badge}>검증 전 가설 · {e.independent_sessions}/{e.minimum_sessions} 독립 거래일</span><p>{e.hypothesis}</p><small>실패 기준: {e.failure_criterion}</small><small>검토 예정 {time(e.review_after)} · 자동 승격 없음</small></article>) : <p className={styles.emptyResearch}>등록된 실험 없음</p>}</div>
  </section>;
}

export function ResearchActivity({ research: r }: { research: Research }) {
  const [archive, setArchive] = useState<Snapshot | null>(null);
  const [archiveError, setArchiveError] = useState(false);
  return <section className={styles.panel}><div className={styles.panelHead}><h2>검토 기록</h2></div>
    <div className={styles.researchFeed}>{r.receipts.length ? r.receipts.slice(0, 8).map(item => <article key={item.proposal_id}><div><span className={`${styles.badge} ${item.status === "accepted" ? styles.ready : styles.waiting}`}>{item.source === "demo" ? "예시 검증 · " : ""}{receiptLabels[item.status] ?? "확인 필요"}</span><time>{time(item.timestamp)}</time></div><p>{item.rationale}</p>{item.status === "rejected" && <small>검증 결과: {receiptReason(item.reason)}</small>}{item.evidence.map(e => <a key={e.evidence_id} href={e.source_url} target="_blank" rel="noopener noreferrer">{e.publisher} · {e.claim}</a>)}</article>) : <p className={styles.emptyResearch}>검토 기록 없음</p>}</div>
    <details className={styles.exchangeHelp}><summary>이전 세션</summary>
    <select aria-label="보관 세션" defaultValue="" onChange={async e => { setArchiveError(false); if (!e.target.value) { setArchive(null); return; } try { setArchive(await paperRequest(`sessions/${e.target.value}`) as Snapshot); } catch { setArchiveError(true); } }}><option value="">보관 기록 선택</option>{r.archives.filter(a => !a.active).map(a => <option key={a.id} value={a.id}>{a.id.slice(0, 12)}</option>)}</select>{archiveError && <p role="alert">보관 기록을 불러오지 못했습니다.</p>}{archive && <Summary session={archive.session} />}</details>
  </section>;
}

function receiptReason(code: string) {
  const reasons: Record<string, string> = { session_inactive: "실행 중인 세션이 없습니다", market_closed: "정규장 운영 시간이 아닙니다", invalid_schema: "제안 형식 또는 고정 위험 한도가 맞지 않습니다", policy_version_conflict: "기준 전략 버전이 변경됐습니다", run_missing_or_expired: "연구 실행의 제한 시간이 지났습니다", stale_context: "상태 자료가 오래됐습니다", evidence_required: "진입 전략을 뒷받침할 근거가 없습니다", beyond_session_close: "유효기간이 세션 종료 시각을 넘습니다", future_evidence: "판단 이후의 근거가 포함됐습니다", invalid_validity: "제안 시각이나 유효기간이 맞지 않습니다", wrong_session: "현재 세션과 다른 제안입니다", validity_exceeds_75_minutes: "제안 유효기간이 75분을 초과했습니다" };
  return reasons[code] ?? "제안 검증을 통과하지 못했습니다. 연구 회신의 상세 코드를 확인하세요.";
}
