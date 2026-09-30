import type { Config, MarketSnapshot, Position } from "./types";
import { priceKrw } from "./validation";

export const feeRate = (market: Config["market"]) => market === "KR" ? 0.00015 : 0.001;

export function mark(position: Position, snapshot: MarketSnapshot, now: number, config: Config) {
  const price = priceKrw(snapshot.quotes[position.symbol], snapshot, now);
  if (price === null) return null;
  const gross = position.shares * price;
  const exitFee = gross * feeRate(config.market);
  return { price, gross, exitFee, liquidation: gross - exitFee, profit: gross - exitFee - position.entryCost };
}

export function valuation(cash: number, positions: Position[], snapshot: MarketSnapshot, now: number, config: Config) {
  const marks = positions.map(position => mark(position, snapshot, now, config));
  if (marks.some(value => value === null)) return null;
  // Entry commissions are already in cash; only anticipated exit fees are deducted here.
  return cash + marks.reduce((total, value) => total + value!.liquidation, 0);
}

export function allocate(symbols: string[], cash: number, snapshot: MarketSnapshot, now: number, config: Config): Position[] {
  const prices = symbols.map(symbol => priceKrw(snapshot.quotes[symbol], snapshot, now));
  if (!symbols.length || prices.some(price => price === null)) return [];
  const rate = feeRate(config.market);
  if (prices.some(price => !Number.isSafeInteger(Math.floor(cash / (price! * (1 + rate)))))) return [];
  const drafts = symbols.map((symbol, i) => {
    const entryPrice = prices[i]!;
    const shares = Math.floor(cash / symbols.length / (entryPrice * (1 + rate)));
    return { symbol, shares, entryPrice, entryFx: snapshot.quotes[symbol]!.currency === "USD" ? snapshot.fx!.rate! : 1,
      entryFee: shares * entryPrice * rate, entryCost: shares * entryPrice * (1 + rate) };
  });
  let remainder = cash - drafts.reduce((sum, position) => sum + position.entryCost, 0);
  while (true) {
    const next = drafts.filter(position => position.entryPrice * (1 + rate) <= remainder)
      .sort((a, b) => a.entryCost - b.entryCost || a.entryPrice - b.entryPrice)[0];
    if (!next) break;
    next.shares++;
    next.entryFee += next.entryPrice * rate;
    next.entryCost += next.entryPrice * (1 + rate);
    remainder -= next.entryPrice * (1 + rate);
  }
  return drafts.filter(position => position.shares > 0);
}
