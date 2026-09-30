export type Market = "KR" | "US";
export type Lifecycle = "idle" | "preparing" | "running" | "paused" | "halted";
export type Condition = "ready" | "warming_up" | "market_closed" | "data_stale" | "provider_cooldown" | "authentication_error";

export interface Instrument { symbol: string; name: string; market: Market }
export interface Theme { id: string; name: string; market: Market; symbols: string[]; curatedRank: number }
export interface Quote {
  price: number | null;
  currency: "KRW" | "USD";
  sourceTime: number;
  receivedAt: number;
  changePercent: number | null;
}
export interface Candle { close: number; closedAt: number; complete: boolean }
export interface History { candles: Candle[]; receivedAt: number }
export interface Fx { rate: number | null; validFrom: number; validUntil: number; receivedAt: number }
export interface MarketSnapshot {
  id: string;
  market: Market;
  observedAt: number;
  quotes: Record<string, Quote | undefined>;
  minute: Record<string, History | undefined>;
  daily: Record<string, History | undefined>;
  fx: Fx | null;
  expectedDailyClose: number;
  marketOpen: boolean;
  closingSoon: boolean;
  provider: "ready" | "cooldown" | "authentication_error";
}
export interface Config { market: Market; capital: number; stopPercent: number; sidecarPercent: number }
export interface Position {
  symbol: string;
  name?: string;
  strategyRef?: string;
  shares: number;
  entryPrice: number;
  entryFx: number;
  entryFee: number;
  entryCost: number;
}
export interface Fill {
  id: string; snapshotId: string; timestamp: number; symbol: string;
  side: "buy" | "sell"; shares: number; priceKrw: number; fx: number;
  fee: number; gross: number; reason: string; netProfit: number | null;
}
export interface SessionEvent {
  id: number; timestamp: number; snapshotId: string | null;
  kind: "command" | "buy" | "sell" | "risk" | "data" | "decision";
  code: string; text: string; symbol?: string;
}
export interface ProfitSample {
  timestamp: number; snapshotId: string; segment: number;
  equity: number; cash: number; holdings: number; profit: number; returnPercent: number;
  priceSourceTime: number | null; fxSourceTime: number | null;
}
export interface Gap { start: number; end: number | null; reason: string }
export interface Session {
  id: string; version: number; evaluatedAt: number; config: Config; lifecycle: Lifecycle; condition: Condition;
  reason: string; baseline: number | null; cash: number; positions: Position[];
  fills: Fill[]; events: SessionEvent[]; samples: ProfitSample[]; gaps: Gap[];
  segment: number; ready: number; total: number; activeTheme: string | null;
  latest: MarketSnapshot | null;
  candidateGroups?: CandidateGroup[];
  standingGroups?: CandidateGroup[];
  candidateChecks?: Record<string, string | null>;
  candidateProposalId?: string | null;
  candidateExpiresAt?: number | null;
  strategyError?: string | null;
}

export interface CandidateGroup {
  group_id: string; name: string;
  candidates: { symbol: string; name: string; rationale: string; evidence_ids: string[]; source_urls?: string[] }[];
}
