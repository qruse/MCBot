import type { Market, MarketSnapshot } from "./types";
import { instruments, themes } from "./universe";
export { instruments, themes } from "./universe";

// Explicit offline fixtures; never a fallback for brokerage data.
const basePrices: Record<string, number> = { "005930": 72000, "000660": 185000, "042700": 115000,
  "114800": 4200, "252670": 2300, "123310": 4100, NVDA: 145, AVGO: 220, AMD: 155, SH: 40, PSQ: 35, SQQQ: 28 };
export type Scenario = "normal" | "candidate_gap" | "stop_with_gap" | "held_stale" | "cooldown" | "closed";
export const scenarios: { value: Scenario; label: string }[] = [
  { value: "normal", label: "Healthy data" }, { value: "candidate_gap", label: "Candidate candles missing" },
  { value: "stop_with_gap", label: "2% stop + candidate gap" }, { value: "held_stale", label: "Held price stale" },
  { value: "cooldown", label: "Provider cooldown" }, { value: "closed", label: "Market closed" },
];

export function fixtureSnapshot(market: Market, now: number, version: number, scenario: Scenario = "normal"): MarketSnapshot {
  const day = 86_400_000;
  const dailyClose = Math.floor(now / day) * day - day;
  const input: MarketSnapshot = { id: `fixture:${market}:${version}`, market, observedAt: now, quotes: {}, minute: {}, daily: {},
    fx: { rate: 1380 + (version % 6), validFrom: now - 1_000, validUntil: now + 300_000, receivedAt: now },
    expectedDailyClose: dailyClose, marketOpen: scenario !== "closed", closingSoon: false,
    provider: scenario === "cooldown" ? "cooldown" : "ready" };
  instruments.filter(item => item.market === market).forEach(item => {
    const theme = themes.find(theme => theme.symbols.includes(item.symbol))!;
    const base = basePrices[item.symbol];
    const inverse = theme.id.endsWith("-inverse");
    const factor = 1 + Math.sin(version * 0.45) * 0.002 + version * 0.00015;
    const first = themes.find(theme => theme.market === market)!.symbols[0];
    input.quotes[item.symbol] = { price: base * (scenario === "stop_with_gap" && item.symbol === first ? 0.965 : factor),
      currency: market === "KR" ? "KRW" : "USD", sourceTime: scenario === "held_stale" && item.symbol === first ? now - 180_000 : now,
      receivedAt: now, changePercent: inverse ? -1 : 1.5 };
    const slope = inverse ? -0.001 : 0.003;
    input.minute[item.symbol] = { receivedAt: now, candles: Array.from({ length: 40 }, (_, i) =>
      ({ close: base * (1 + (i - 39) * slope), closedAt: now - (40 - i) * 60_000, complete: true })) };
    input.daily[item.symbol] = { receivedAt: now, candles: Array.from({ length: 100 }, (_, i) =>
      ({ close: base * (1 + (i - 99) * slope), closedAt: dailyClose - (99 - i) * day, complete: true })) };
  });
  if (scenario === "candidate_gap" || scenario === "stop_with_gap") {
    const candidate = themes.filter(theme => theme.market === market)[1].symbols[0];
    delete input.minute[candidate];
  }
  return input;
}
