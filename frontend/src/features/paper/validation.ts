import type { History, MarketSnapshot, Quote } from "./types";

export const positive = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value) && value > 0;
const fresh = (timestamp: number, now: number, age: number) =>
  positive(timestamp) && timestamp <= now + 5_000 && now - timestamp <= age;

export function quoteIssue(quote: Quote | undefined, snapshot: MarketSnapshot, now: number): string | null {
  if (!quote || !positive(quote.price)) return "Missing or invalid price";
  if (quote.currency !== "KRW" && quote.currency !== "USD") return "Unknown quote currency";
  if (quote.currency !== (snapshot.market === "KR" ? "KRW" : "USD")) return "Quote currency does not match the execution market";
  if (!fresh(quote.receivedAt, now, 90_000)) return "Quote transport is stale";
  if (!fresh(quote.sourceTime, now, 90_000)) return "Price source timestamp is stale or invalid";
  if (quote.currency === "USD") {
    const fx = snapshot.fx;
    if (!fx || !positive(fx.rate) || !fresh(fx.receivedAt, now, 360_000)
      || !positive(fx.validFrom) || !positive(fx.validUntil)
      || fx.validFrom > now || fx.validUntil < now) return "USD/KRW is missing, expired or invalid";
    if (!positive(quote.price * fx.rate!)) return "Converted price is invalid";
  }
  return null;
}

export function priceKrw(quote: Quote | undefined, snapshot: MarketSnapshot, now: number): number | null {
  if (quoteIssue(quote, snapshot, now)) return null;
  return quote!.price! * (quote!.currency === "USD" ? snapshot.fx!.rate! : 1);
}

export function historyIssue(history: History | undefined, interval: "minute" | "daily", snapshot: MarketSnapshot, now: number): string | null {
  const minimum = interval === "minute" ? 26 : 80;
  if (!history || history.candles.length < minimum) return `Need ${minimum} complete ${interval} candles`;
  if (!fresh(history.receivedAt, now, interval === "minute" ? 1_200_000 : 4_200_000)) return `${interval} history transport is stale`;
  let previous = 0;
  for (const candle of history.candles) {
    if (!positive(candle.close) || !positive(candle.closedAt) || candle.closedAt > now
      || candle.closedAt <= previous || !candle.complete) return `Invalid or incomplete ${interval} candle`;
    previous = candle.closedAt;
  }
  if (interval === "minute" && now - previous > 1_200_000) return "Minute candle source is stale";
  if (interval === "daily" && (!positive(snapshot.expectedDailyClose) || previous < snapshot.expectedDailyClose)) return "Daily candle source is behind the expected close";
  return null;
}

export function strategyIssue(symbol: string, snapshot: MarketSnapshot, now: number): string | null {
  return quoteIssue(snapshot.quotes[symbol], snapshot, now)
    || historyIssue(snapshot.minute[symbol], "minute", snapshot, now)
    || historyIssue(snapshot.daily[symbol], "daily", snapshot, now)
    || (!Number.isFinite(snapshot.quotes[symbol]?.changePercent) ? "Daily price change is unknown" : null);
}
