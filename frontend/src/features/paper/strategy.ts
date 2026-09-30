import type { Candle, MarketSnapshot, Theme } from "./types";
import { historyIssue } from "./validation";

function average(candles: Candle[], count: number) {
  const values = candles.slice(-count);
  return values.reduce((sum, candle) => sum + candle.close, 0) / values.length;
}
export function trend(candles: Candle[], fastWindow = 8, slowWindow = 26, offset = 4) {
  const fast = average(candles, fastWindow);
  const previousFast = average(candles.slice(0, -offset), fastWindow);
  const slow = average(candles, slowWindow);
  const score = (fast - slow) / slow * 100 + (fast - previousFast) / previousFast * 200;
  return { fast, previousFast, slow, score, rising: fast > previousFast && fast > slow };
}
function longScore(symbol: string, snapshot: MarketSnapshot) {
  const candles = snapshot.daily[symbol]!.candles;
  return trend(candles, 20, 60, 8).score * 0.45 + trend(candles, 20, 80, 10).score * 0.55;
}
function score(symbol: string, snapshot: MarketSnapshot) {
  const short = trend(snapshot.minute[symbol]!.candles);
  return short.score * (short.rising ? 1 : 0.35) + longScore(symbol, snapshot) * 0.65
    + snapshot.quotes[symbol]!.changePercent! * 0.15;
}
export function rankThemes(themes: Theme[], snapshot: MarketSnapshot) {
  return themes.map(theme => {
    const leaders = theme.symbols.slice(0, 5);
    const momentum = leaders.reduce((sum, symbol) => sum + score(symbol, snapshot), 0) / leaders.length;
    const targets = theme.symbols.slice(0, 3);
    const rising = targets.filter(symbol => trend(snapshot.minute[symbol]!.candles).rising && longScore(symbol, snapshot) > 0).length;
    return { theme, momentum, eligible: momentum > 0.12 && rising >= Math.ceil(targets.length * 0.6) };
  }).sort((a, b) => b.momentum - a.momentum);
}
export function maBroken(symbol: string, snapshot: MarketSnapshot, now: number): boolean | null {
  if (historyIssue(snapshot.minute[symbol], "minute", snapshot, now)) return null;
  const value = trend(snapshot.minute[symbol]!.candles);
  return value.fast < value.slow * 0.998 || (value.fast < value.previousFast * 0.99875 && value.score < 0);
}
export function themeRollover(theme: Theme, snapshot: MarketSnapshot, now: number) {
  const leaders = theme.symbols.slice(0, 5);
  if (leaders.some(symbol => historyIssue(snapshot.minute[symbol], "minute", snapshot, now)
    || historyIssue(snapshot.daily[symbol], "daily", snapshot, now)
    || !Number.isFinite(snapshot.quotes[symbol]?.changePercent))) return false;
  const momentum = leaders.reduce((sum, symbol) => sum + score(symbol, snapshot), 0) / leaders.length;
  const falling = leaders.filter(symbol => {
    const value = trend(snapshot.minute[symbol]!.candles);
    return value.fast < value.slow * 0.996 && value.fast < value.previousFast * 0.9975 && value.score < -0.18;
  }).length;
  return momentum < 0 && falling >= Math.ceil(leaders.length * 0.7);
}
