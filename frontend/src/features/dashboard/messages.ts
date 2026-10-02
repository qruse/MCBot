import type { Session, SessionEvent } from "../paper/types";
import type { Scenario } from "../paper/fixtures";
import type { ConnectionState } from "../market/toss";

export function connectionMessage(connection: ConnectionState, paused: boolean) {
  if (connection.state === "authentication_error") return connection.issue === "missing_credentials"
    ? "API 키가 없습니다. 서버의 환경 설정을 확인하고 백엔드를 재시작한 뒤 새 모의매매를 시작해 주세요."
    : "인증 또는 허용 IP를 확인해야 합니다. API 요청을 중지했습니다. 설정 수정과 백엔드 재시작 후 새 모의매매를 시작해 주세요.";
  if (connection.state === "cooldown") return `${connection.issue === "backend" ? "데이터 서버에 연결하지 못했습니다." : "API 오류 또는 요청 제한으로 대기합니다."} ${connection.retryAt ? new Date(connection.retryAt).toLocaleTimeString("ko-KR", { hour12: false, timeZone: "Asia/Seoul" }) : "대기 종료"} 이후 재시도합니다.`;
  if (paused) return "일시정지 중에는 API 수집과 모의매매를 멈춥니다.";
  if (connection.state === "loading") return "토스증권 데이터를 순서대로 확인하고 있습니다. 처음에는 준비 시간이 필요합니다.";
  if (connection.state === "ready") return "토스증권 API 연결됨 · 시세 30초, 전략 데이터 15분 간격으로 갱신합니다.";
  return "모의매매 시작 버튼을 누르면 API에 연결합니다.";
}

// Keep English domain messages and identifiers intact; localize at the presentation boundary.
export const labels: Record<string, string> = {
  idle: "시작 전", preparing: "준비 중", running: "실행 중", paused: "일시정지", halted: "위험으로 중단",
  ready: "데이터 준비 완료", warming_up: "데이터 준비 중", market_closed: "장 마감",
  data_stale: "시세 확인 필요", provider_cooldown: "요청 제한으로 대기", authentication_error: "인증 확인 필요",
  command: "실행 제어", buy: "매수", sell: "매도", risk: "위험 감지", data: "데이터", decision: "매매 판단",
};
export const instrumentNames: Record<string, string> = {
  "069500": "KODEX 200", "360750": "TIGER 미국S&P500", "148070": "KIWOOM 국고채10년", "411060": "ACE KRX금현물",
  "005930": "삼성전자", "000660": "SK하이닉스", "042700": "한미반도체", "012450": "한화에어로스페이스",
  "079550": "LIG넥스원", "064350": "현대로템", "267260": "HD현대일렉트릭", "114800": "KODEX 인버스", "252670": "KODEX 200선물인버스2X",
  "123310": "TIGER 인버스", NVDA: "엔비디아", AVGO: "브로드컴", AMD: "AMD", MSFT: "마이크로소프트",
  GOOGL: "알파벳", META: "메타", SH: "프로셰어즈 S&P500 인버스", PSQ: "프로셰어즈 나스닥100 인버스",
  SQQQ: "프로셰어즈 나스닥100 인버스 3배", "145670": "ACE 인버스", DOG: "프로셰어즈 다우30 인버스",
};
export const themeNames: Record<string, string> = {
  "kr-standing-inverse-v1": "상시 국내 인버스", "us-standing-inverse-v1": "상시 미국 인버스",
  "kr-semis": "국내 반도체", "kr-defense": "국내 방산", "kr-inverse": "국내 인버스 ETF",
  "us-semis": "AI 반도체", "us-platforms": "AI 플랫폼", "us-inverse": "미국 인버스 ETF",
};
export const scenarioNames: Record<Scenario, string> = {
  normal: "정상 데이터", candidate_gap: "후보 종목 캔들 누락", stop_with_gap: "2% 손절 · 후보 데이터 누락",
  held_stale: "보유 종목 시세 지연", cooldown: "API 요청 제한으로 대기", closed: "장 마감",
};

const translations: Record<string, string> = {
  index_inverse_unverified: "인버스 배율 확인 대기",
  index_inverse_ineligible: "일일 -1배 지수 인버스 검증 미통과",
  index_inverse_not_admitted: "지수 인버스 대상 제외",
  portfolio_rebalance: "목표 비중 조정",
  portfolio_rotation: "종목 교체",
  general_etf_excluded: "일반 ETF는 투자 대상에서 제외",
  enable_continuous: "지속 모의운용 설정",
  closing_exit_incomplete: "장 마감 청산 미완료 · 운용 정지",
  instrument_unverified: "종목 정보 확인 대기",
  instrument_ineligible: "시장·상품·거래 상태 검증 미통과",
  candidate_quote_unavailable: "유효한 시세·환율 대기",
  candidate_history_pending: "분봉·일봉 준비 중",
  candidate_change_pending: "등락률 확인 대기",
  ready: "전략 데이터가 준비됐습니다. 유효한 전략과 다음 시세를 확인합니다.",
  warming_up: "필요한 시세와 이력을 준비하고 있습니다. 준비 전에는 신규 진입을 하지 않습니다.",
  market_closed: "정규장 운영 시간이 아닙니다. 모의 주문을 체결하지 않습니다.",
  data_stale: "시세 또는 환율이 유효하지 않아 평가와 일부 위험 점검이 제한됩니다.",
  provider_cooldown: "데이터 공급자 대기 중입니다. 유효한 보유 시세의 위험 점검은 유지합니다.",
  authentication_error: "시세 인증을 확인해 주세요. 인증 복구 후 서버를 재시작해야 합니다.",
  start: "서버 모의매매를 시작했습니다.", prepared: "초기 자산을 확정하고 수익 기록을 시작했습니다.",
  pause: "시뮬레이션과 위험 점검을 모두 정지했습니다.", resume: "기존 원장과 기준금액으로 재개했습니다.",
  pause_entries: "신규 진입을 중지했습니다. 보유 종목 위험 점검은 계속합니다.",
  resume_entries: "유효한 전략에 따른 신규 진입을 허용했습니다.",
  user_pause: "사용자 정지 · 위험 점검과 수익 기록 중지",
  restart_paused: "서버 재시작 · 기록 복원 후 일시정지",
  standing_candidates_added: "일반 후보와 별도로 상시 인버스 후보를 추가했습니다.",
  manual_research_requested: "사용자 요청으로 전략을 다시 검토합니다.",
  strategy_execution_failed: "전략 코드 실행 실패 · 신규 진입을 중지하고 공통 위험 점검을 유지합니다.",
  strategy_rollback: "이전 전략 코드 버전으로 되돌렸습니다. 기존 보유분의 진입 버전은 유지합니다.",
  strategy_exit: "전략 모듈의 청산 조건을 충족해 매도했습니다.",
  session_lease_expired: "장 종료 또는 실행 기한 만료 · 일시정지",
  engine_tick_failed: "서버 처리 오류 · 기록 보존 후 일시정지",
  theme_entry: "상승 테마 상위 3종목 · 다음 유효 시세에서 모의 매수",
  position_stop: "개별 종목 손실 2% · 모의 손절",
  sidecar_halt: "보유분 전체 손실 5% · 청산 및 자동 중단",
  closing_exit: "장 마감 5분 전 · 모의 청산",
  ma_exit: "보유 종목 이동평균 이탈 · 모의 청산",
  theme_rollover: "테마 추세 하락 · 모의 청산",
  theme_rotation: "상위 테마 교체 · 기존 종목 모의 청산",
  policy_accepted: "Codex 전략 제안을 검증하고 적용했습니다. 기존 보유분의 위험 한도는 유지합니다.",
  policy_observed: "Codex 제안을 관찰 기록으로 남겼습니다. 실행 전략은 변경하지 않았습니다.",
  policy_rejected: "Codex 제안이 검증을 통과하지 못했습니다. 연구 회신을 확인해 주세요.",
  "Missing or invalid price": "가격이 없거나 유효하지 않습니다",
  "Unknown quote currency": "가격의 통화를 확인할 수 없습니다",
  "Quote currency does not match the execution market": "가격의 통화가 선택한 시장과 다릅니다",
  "Quote transport is stale": "시세 수신이 지연되고 있습니다",
  "Price source timestamp is stale or invalid": "시세 기준 시각이 오래됐거나 유효하지 않습니다",
  "USD/KRW is missing, expired or invalid": "원·달러 환율이 없거나 유효기간이 지났습니다",
  "Converted price is invalid": "원화 환산 가격이 유효하지 않습니다",
  "Minute candle source is stale": "최근 분봉 데이터가 없습니다",
  "Daily candle source is behind the expected close": "최근 거래일의 일봉 데이터가 없습니다",
  "Daily price change is unknown": "일간 등락률을 확인할 수 없습니다",
  "No snapshot": "시세 데이터가 없습니다", "No history": "캔들 데이터가 없습니다",
  "Waiting for data": "데이터를 기다리고 있습니다",
  "Waiting for a market snapshot.": "시세 데이터를 기다리고 있습니다.",
  "Start a paper session to prepare the strategy.": "모의매매를 시작하면 전략 데이터를 확인합니다.",
  "Provider authentication failed. Fix access before retrying.": "데이터 공급자 인증에 실패했습니다. 인증 정보를 확인해 주세요.",
  "Provider is cooling down; new entries are blocked. Cached valid risk checks remain available.": "API 요청 제한으로 대기 중입니다. 신규 매수는 멈추고, 유효한 기존 시세로 보유 종목의 위험을 확인합니다.",
  "Market session is closed. No simulated fills.": "장이 닫혀 있습니다. 모의 주문을 체결하지 않습니다.",
  "Held-price or FX data is invalid. Profit sampling is suspended; valid individual risk checks continue.": "보유 종목의 시세나 환율을 확인할 수 없어 수익 기록을 멈췄습니다. 유효한 시세가 있는 종목의 위험 검사는 계속합니다.",
  "Closing window: entries blocked and valid holdings exited.": "장 마감 5분 전입니다. 신규 매수를 멈추고, 유효한 시세가 있는 보유 종목을 청산합니다.",
  "Strategy inputs are ready. Waiting for the next unique market snapshot.": "전략 데이터가 준비됐습니다. 다음 시세 갱신 때 매매 조건을 확인합니다.",
  "User paused decisions, risk checks and profit sampling. Resume keeps the original baseline.": "매매 판단·위험 검사·수익 기록을 일시정지했습니다. 재개해도 시작 기준금액은 유지됩니다.",
  "Portfolio sidecar halted this session. Review the risk event and acknowledge before creating a new session.": "보유 종목 전체 손실이 5%에 도달해 자동 중단됐습니다. 위험 기록을 확인한 뒤 새 모의매매를 시작해 주세요.",
  "User pause: risk checks and samples stopped": "사용자 일시정지 · 위험 검사와 수익 기록 중지",
  "Held price or FX is stale / missing": "보유 종목 시세 또는 환율 누락·지연",
  "Portfolio sidecar halt": "보유 종목 전체 손실 5%로 자동 중단",
  "Paper session requested; configuration and baseline belong to this session.": "모의매매를 시작합니다. 현재 설정과 시작 기준금액을 사용합니다.",
  "Paper session paused.": "모의매매를 일시정지했습니다.",
  "Resumed with the original configuration and profit baseline.": "기존 설정과 시작 기준금액을 유지하며 모의매매를 재개했습니다.",
  "Preparation complete; initial liquidation-equity baseline recorded.": "준비가 완료됐습니다. 시작 시점의 순평가자산을 수익 기준금액으로 기록했습니다.",
  "Snapshot identity, market or observation time is invalid; previous inputs retained.": "시장 정보나 시세 시각이 유효하지 않아 새 데이터를 반영하지 않았습니다.",
  "Aggregate sidecar needs valid prices for every holding; valid individual stops still run.": "전체 손실 검사는 모든 보유 종목의 유효한 시세가 필요합니다. 확인 가능한 종목의 손절 검사는 계속합니다.",
  "5% holding-loss sidecar triggered. Explicit acknowledgement is required for a new session.": "보유 종목 전체 손실이 5%에 도달해 매매를 중단했습니다. 위험 기록을 확인한 뒤 새 모의매매를 시작해 주세요.",
  "Complete candidate set has no qualifying uptrend; no entry.": "모든 후보를 확인했지만 매수 조건을 충족하는 상승 테마가 없어 기다립니다.",
  "Portfolio sidecar": "보유 종목 전체 손실 5%로 자동 청산",
  "Five-minute closing window": "장 마감 5분 전 청산",
  "Position stop loss": "개별 종목 손실 2%로 손절",
  "Held-stock moving-average break": "보유 종목의 이동평균 이탈",
  "Theme moving-average rollover": "테마의 이동평균 추세 하락",
  "Rotation to the leading theme": "더 강한 상승 테마로 교체",
  "Leading uptrend theme / balanced TOP3": "상승 테마의 상위 3종목 균등 배분",
};

export function message(text: string): string {
  if (translations[text]) return translations[text];
  const progress = text.match(/^Strategy ready (\d+)\/(\d+)\./);
  if (progress) return `전략 데이터 ${progress[1]}/${progress[2]}개 준비. 신규 매수는 기다리며, 보유 종목의 위험 검사는 계속합니다.`;
  const needed = text.match(/^Need (\d+) complete (minute|daily) candles$/);
  if (needed) return `완료된 ${needed[2] === "minute" ? "분봉" : "일봉"} ${needed[1]}개가 필요합니다`;
  const stale = text.match(/^(minute|daily) history transport is stale$/);
  if (stale) return `${stale[1] === "minute" ? "분봉" : "일봉"} 수신이 지연되고 있습니다`;
  const invalid = text.match(/^Invalid or incomplete (minute|daily) candle$/);
  if (invalid) return `${invalid[1] === "minute" ? "분봉" : "일봉"}이 유효하지 않거나 아직 완료되지 않았습니다`;
  return "데이터 상태를 확인해 주세요.";
}

export function executionReason(session: Session) {
  if (session.lifecycle === "idle" && session.condition === "ready") return "전략 데이터가 준비됐습니다. 모의매매를 시작해 주세요.";
  if (session.condition === "warming_up" && ["idle", "preparing"].includes(session.lifecycle)) {
    return `전략 데이터 ${session.ready}/${session.total}개 준비. 나머지 데이터를 기다리고 있습니다. 준비가 완료되면 수익 기록을 시작합니다.`;
  }
  return message(session.reason);
}

export function eventMessage(event: SessionEvent) {
  if (event.code === "theme_entry" || event.code === "position_exit") {
    const fill = event.text.match(/^(Bought|Sold) (\d+) (\S+): (.+)\.$/);
    if (fill) return `${instrumentNames[fill[3]] ?? fill[3]} ${Number(fill[2]).toLocaleString("ko-KR")}주 ${fill[1] === "Bought" ? "매수" : "매도"} · ${message(fill[4])}`;
  }
  if (event.code === "risk_unavailable") {
    const issue = event.text.match(/^[^:]+: (.+)\. No fill;/);
    return `${instrumentNames[event.symbol ?? ""] ?? event.symbol ?? "보유 종목"} · ${issue ? message(issue[1]) : "시세를 확인할 수 없습니다"}. 체결과 위험 검사를 진행할 수 없습니다.`;
  }
  if (event.code === "fill_refused") return `${instrumentNames[event.symbol ?? ""] ?? event.symbol ?? "보유 종목"} · 가격이나 환율이 유효하지 않아 청산하지 못했습니다.`;
  return message(event.text);
}
