import type { Config, MarketSnapshot, Position } from "./types";
import { mark } from "./accounting";
import { maBroken } from "./strategy";
import { quoteIssue } from "./validation";

/** Candidate readiness must never gate this function. Each holding has its own inputs. */
export function inspectRisk(positions: Position[], snapshot: MarketSnapshot, now: number, config: Config) {
  const marks = positions.map(position => mark(position, snapshot, now, config));
  const complete = marks.every(value => value !== null);
  const sidecar = positions.length > 0 && complete && marks.reduce((sum, value) => sum + value!.liquidation, 0)
    <= positions.reduce((sum, position) => sum + position.entryCost, 0) * (1 - config.sidecarPercent / 100);
  const exits: { symbol: string; reason: string }[] = [];
  const unavailable: { symbol: string; reason: string }[] = [];
  positions.forEach((position, index) => {
    const value = marks[index];
    if (!value) {
      unavailable.push({ symbol: position.symbol, reason: quoteIssue(snapshot.quotes[position.symbol], snapshot, now)! });
      return;
    }
    if (sidecar) exits.push({ symbol: position.symbol, reason: "Portfolio sidecar" });
    else if (snapshot.closingSoon) exits.push({ symbol: position.symbol, reason: "Five-minute closing window" });
    else if (value.liquidation <= position.entryCost * (1 - config.stopPercent / 100)) exits.push({ symbol: position.symbol, reason: "Position stop loss" });
    else if (maBroken(position.symbol, snapshot, now)) exits.push({ symbol: position.symbol, reason: "Held-stock moving-average break" });
  });
  return { exits, unavailable, sidecar, sidecarAvailable: complete };
}
