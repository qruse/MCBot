import type { Instrument, Market, Theme } from "./types";

// Bounded production candidates. Sample quotes exist only in fixtures.ts.
export const instruments: Instrument[] = [
  { symbol: "005930", name: "Samsung Electronics", market: "KR" },
  { symbol: "000660", name: "SK hynix", market: "KR" },
  { symbol: "042700", name: "Hanmi Semiconductor", market: "KR" },
  { symbol: "114800", name: "KODEX Inverse", market: "KR" },
  { symbol: "252670", name: "KODEX 200 Futures Inverse 2X", market: "KR" },
  { symbol: "123310", name: "TIGER Inverse", market: "KR" },
  { symbol: "NVDA", name: "NVIDIA", market: "US" },
  { symbol: "AVGO", name: "Broadcom", market: "US" },
  { symbol: "AMD", name: "Advanced Micro Devices", market: "US" },
  { symbol: "SH", name: "ProShares Short S&P500", market: "US" },
  { symbol: "PSQ", name: "ProShares Short QQQ", market: "US" },
  { symbol: "SQQQ", name: "ProShares UltraPro Short QQQ", market: "US" },
];
export const themes: Theme[] = [
  { id: "kr-semis", name: "Korea Semiconductors", market: "KR", symbols: ["005930", "000660", "042700"], curatedRank: 1 },
  { id: "kr-inverse", name: "Korea Inverse ETFs", market: "KR", symbols: ["114800", "252670", "123310"], curatedRank: 2 },
  { id: "us-semis", name: "AI Semiconductors", market: "US", symbols: ["NVDA", "AVGO", "AMD"], curatedRank: 1 },
  { id: "us-inverse", name: "US Inverse ETFs", market: "US", symbols: ["SH", "PSQ", "SQQQ"], curatedRank: 2 },
];

export function marketInstruments(market: Market) {
  return instruments.filter(instrument => instrument.market === market);
}
