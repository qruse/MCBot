import type { History, Market, MarketSnapshot } from "../paper/types";

type Period = { startTime: string; endTime: string };
type CalendarDay = { date: string; integrated?: { regularMarket: Period | null } | null; regularMarket?: Period | null };
export interface CalendarResponse { data: { today: CalendarDay; previousBusinessDay: CalendarDay; nextBusinessDay: CalendarDay }; synced_at: string }
interface Quality { valid: boolean; source_at: string; received_at: string; valid_until?: string }
export interface PricesResponse {
  data: { symbol: string; lastPrice: string; currency: "KRW" | "USD"; timestamp: string }[];
  quality: Record<string, Quality>; usd_krw: string | null; fx_quality: Quality | null; synced_at: string;
  provider_status?: { state: MarketSnapshot["provider"]; retry_after_seconds: number | null };
}
interface RawCandle { closePrice: string; timestamp: string }
export interface StrategyResponse {
  minute: RawCandle[]; daily: RawCandle[]; synced_at: string;
  quality: Record<"minute" | "daily", { received_at: string; valid_values: boolean }>;
}
export interface ConnectionState {
  state: "idle" | "loading" | "ready" | "cooldown" | "authentication_error";
  issue: "none" | "connecting" | "missing_credentials" | "authentication" | "backend" | "rate_limit" | "provider";
  retryAt: number | null;
}
export const idleConnection: ConnectionState = { state: "idle", issue: "none", retryAt: null };
const period = (day: CalendarDay, market: Market) => market === "KR" ? day.integrated?.regularMarket : day.regularMarket;
const positive = (value: string | null | undefined) => value != null && value.trim() !== "" && Number.isFinite(Number(value)) && Number(value) > 0 ? Number(value) : null;
const candleDate = (timestamp: string, market: Market) => {
  const parsed = Date.parse(timestamp);
  if (!Number.isFinite(parsed)) return "";
  return new Intl.DateTimeFormat("en-CA", { timeZone: market === "KR" ? "Asia/Seoul" : "America/New_York",
    year: "numeric", month: "2-digit", day: "2-digit" }).format(parsed);
};

export function calendarState(calendar: CalendarResponse, market: Market, now: number) {
  const days = [calendar.data.previousBusinessDay, calendar.data.today, calendar.data.nextBusinessDay];
  const current = days.find(day => {
    const hours = period(day, market);
    return hours && Date.parse(hours.startTime) <= now && now < Date.parse(hours.endTime);
  });
  const completed = days.filter(day => period(day, market) && Date.parse(period(day, market)!.endTime) <= now)
    .sort((a, b) => Date.parse(period(b, market)!.endTime) - Date.parse(period(a, market)!.endTime))[0];
  const close = current ? Date.parse(period(current, market)!.endTime) : 0;
  return { marketOpen: !!current, closingSoon: !!current && close - now <= 300_000,
    expectedDailyClose: completed ? Date.parse(period(completed, market)!.endTime) : 0,
    completedDate: completed?.date ?? "" };
}

function history(raw: RawCandle[], interval: "minute" | "daily", response: StrategyResponse, state: ReturnType<typeof calendarState>, now: number, market: Market): History {
  const candles = response.quality[interval].valid_values ? raw.map(candle => {
    const date = candleDate(candle.timestamp, market);
    const closedAt = interval === "minute" ? Date.parse(candle.timestamp) + 60_000
      : date === state.completedDate ? state.expectedDailyClose : Date.parse(candle.timestamp) + 86_400_000;
    return { close: positive(candle.closePrice) ?? NaN, closedAt,
      complete: closedAt <= now && (interval === "minute" || date <= state.completedDate) };
  }).filter(candle => candle.complete).sort((a, b) => a.closedAt - b.closedAt) : [];
  return { candles, receivedAt: Date.parse(response.quality[interval].received_at) };
}

export function tossSnapshot(market: Market, calendar: CalendarResponse | null, prices: PricesResponse | null,
  histories: Record<string, StrategyResponse>, provider: MarketSnapshot["provider"], now: number): MarketSnapshot {
  const state = calendar ? calendarState(calendar, market, now) : { marketOpen: false, closingSoon: false, expectedDailyClose: 0, completedDate: "" };
  const input: MarketSnapshot = { id: "", market, observedAt: now, quotes: {}, minute: {}, daily: {}, fx: null, ...state, provider };
  for (const [symbol, response] of Object.entries(histories)) {
    input.minute[symbol] = history(response.minute, "minute", response, state, now, market);
    input.daily[symbol] = history(response.daily, "daily", response, state, now, market);
  }
  for (const quote of prices?.data ?? []) {
    const quality = prices!.quality[quote.symbol];
    const price = quality?.valid ? positive(quote.lastPrice) : null;
    const daily = histories[quote.symbol]?.daily.find(candle => candleDate(candle.timestamp, market) === state.completedDate);
    const previous = positive(daily?.closePrice);
    input.quotes[quote.symbol] = { price, currency: quote.currency, sourceTime: Date.parse(quote.timestamp),
      receivedAt: Date.parse(quality?.received_at ?? ""), changePercent: price && previous ? (price / previous - 1) * 100 : null };
  }
  const fx = prices?.fx_quality;
  if (fx?.valid) input.fx = { rate: positive(prices!.usd_krw), validFrom: Date.parse(fx.source_at),
    validUntil: Date.parse(fx.valid_until ?? ""), receivedAt: Date.parse(fx.received_at) };
  // Identity describes decision inputs, never the five-second sampling clock.
  input.id = `toss:${JSON.stringify({ market, provider, ...state, calendar: calendar?.synced_at,
    prices: prices?.synced_at, quotes: input.quotes, fx: input.fx,
    histories: Object.entries(histories).map(([symbol, value]) => [symbol, value.quality]) })}`;
  return input;
}

class DataFailure extends Error {
  constructor(public connection: ConnectionState) { super(connection.issue); }
}

/** One non-overlapping queue per session. The backend globally paces and caches every upstream call. */
export class TossCollector {
  private controller: AbortController | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private calendar: CalendarResponse | null = null;
  private prices: PricesResponse | null = null;
  private histories: Record<string, StrategyResponse> = {};
  private refreshed: Record<string, number> = {};
  private calendarAt = 0;
  private pricesAt = 0;
  private connection = idleConnection;
  private lastIdentity = "";
  private revision = 0;

  constructor(private market: Market, private symbols: string[], private base: string,
    private heldSymbols: () => string[], private onSnapshot: (snapshot: MarketSnapshot) => void,
    private onConnection: (state: ConnectionState) => void) {}

  start() {
    if (this.controller) return;
    this.controller = new AbortController();
    void this.tick(this.controller.signal);
  }
  stop() {
    this.controller?.abort(); this.controller = null;
    if (this.timer) clearTimeout(this.timer);
  }
  private async request<T>(path: string, signal: AbortSignal): Promise<T> {
    let response: Response;
    try {
      response = await fetch(`${this.base}/brokers/toss/${path}`, { cache: "no-store", signal: AbortSignal.any([signal, AbortSignal.timeout(45_000)]) });
    } catch (error) {
      if (signal.aborted) throw error;
      throw new DataFailure({ state: "cooldown", issue: "backend", retryAt: Date.now() + 60_000 });
    }
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      const authentication = response.headers.get("X-Toss-State") === "authentication_error";
      const retry = Number(response.headers.get("Retry-After"));
      throw new DataFailure({ state: authentication ? "authentication_error" : "cooldown",
        issue: authentication ? String(body.detail).includes("Set TOSS_") ? "missing_credentials" : "authentication"
          : response.status === 503 ? "rate_limit" : "provider",
        retryAt: authentication ? null : Date.now() + Math.max(response.status === 503 ? 300 : 60, Number.isFinite(retry) ? retry : 60) * 1000 });
    }
    return response.json();
  }
  private publish(now: number) {
    const provider = this.connection.state === "authentication_error" ? "authentication_error" : this.connection.state === "cooldown" ? "cooldown" : "ready";
    const input = tossSnapshot(this.market, this.calendar, this.prices, this.histories, provider, now);
    if (input.id !== this.lastIdentity) {
      this.lastIdentity = input.id;
      input.id = `toss:${this.market}:${++this.revision}:${now}`;
      this.onSnapshot(input);
    }
    this.onConnection({ ...this.connection });
  }
  private async tick(signal: AbortSignal) {
    if (signal.aborted) return;
    const now = Date.now();
    try {
      if (this.connection.state === "authentication_error" || (this.connection.retryAt && now < this.connection.retryAt)) return;
      const open = this.calendar && calendarState(this.calendar, this.market, now).marketOpen;
      const ordered = [...new Set([...this.heldSymbols(), ...this.symbols])];
      const symbol = ordered.find(item => !this.refreshed[item] || now - this.refreshed[item] >= 900_000);
      const calendarDue = !this.calendar || now - this.calendarAt >= 3_600_000;
      const pricesDue = !this.prices || now - this.pricesAt >= 30_000;
      if (!calendarDue && (!open || (!pricesDue && !symbol))) return;
      this.connection = { state: "loading", issue: "connecting", retryAt: null };
      this.onConnection(this.connection);
      if (calendarDue) {
        this.calendar = await this.request<CalendarResponse>(`calendar/${this.market}`, signal);
        this.calendarAt = Date.now();
      } else if (open) {
        // Quote batches always take priority over sequential candidate history jobs.
        if (pricesDue) {
          this.prices = await this.request<PricesResponse>(`prices?symbols=${this.symbols.join(",")}`, signal);
          this.pricesAt = Date.now();
          const status = this.prices.provider_status;
          if (status && status.state !== "ready") throw new DataFailure({ state: status.state, issue: status.state === "authentication_error" ? "authentication" : "provider",
            retryAt: status.state === "authentication_error" ? null : Date.now() + Math.max(60, status.retry_after_seconds ?? 60) * 1000 });
        } else {
          if (symbol) {
            this.histories[symbol] = await this.request<StrategyResponse>(`strategy/${encodeURIComponent(symbol)}`, signal);
            this.refreshed[symbol] = Date.now();
          }
        }
      }
      this.connection = { state: "ready", issue: "none", retryAt: null };
    } catch (error) {
      if (!signal.aborted) this.connection = error instanceof DataFailure ? error.connection
        : { state: "cooldown", issue: "provider", retryAt: Date.now() + 60_000 };
    } finally {
      if (!signal.aborted) {
        this.publish(Date.now());
        // Stop automatic authentication retries. Pausing/resuming does not bypass this latch.
        if (this.connection.state !== "authentication_error") this.timer = setTimeout(() => void this.tick(signal), 1000);
      }
    }
  }
}
