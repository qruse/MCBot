import type { MarketSnapshot, Position, Config, Session } from "../paper/types";
import { feeRate } from "../paper/accounting";
import { positive, quoteIssue } from "../paper/validation";

// Presentation only. The execution engine continues to use priceKrw/mark and fresh quotes.
export function displayMark(position: Position, snapshot: MarketSnapshot, now: number, config: Config) {
  const quote = snapshot.displayQuotes?.[position.symbol] ?? snapshot.quotes[position.symbol];
  if (!quote || !positive(quote.price) || !positive(quote.sourceTime)
    || quote.sourceTime > now || now - quote.sourceTime > 7 * 86_400_000
    || quote.currency !== (config.market === "KR" ? "KRW" : "USD")) return null;
  const fx = snapshot.fx;
  if (quote.currency === "USD" && (!fx || !positive(fx.rate) || fx.validFrom > now
    || fx.validUntil < now || now - fx.receivedAt > 360_000)) return null;
  const price = quote.price * (quote.currency === "USD" ? fx!.rate! : 1);
  const gross = position.shares * price;
  const liquidation = gross * (1 - feeRate(config.market));
  return { price, liquidation, profit: liquidation - position.entryCost, sourceTime: quote.sourceTime,
    delayed: quoteIssue(quote, snapshot, now) !== null };
}

export function displayValuation(session: Session) {
  if (!session.positions.length) return { equity: session.cash, sourceTime: null, delayed: false };
  if (!session.latest) return null;
  const marks = session.positions.map(p => displayMark(p, session.latest!, session.evaluatedAt, session.config));
  if (marks.some(mark => !mark)) return null;
  return { equity: session.cash + marks.reduce((sum, mark) => sum + mark!.liquidation, 0),
    sourceTime: Math.min(...marks.map(mark => mark!.sourceTime)), delayed: marks.some(mark => mark!.delayed) };
}
