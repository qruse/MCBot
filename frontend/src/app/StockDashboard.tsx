"use client";

import {
  Activity,
  BarChart3,
  Bell,
  Bot,
  Briefcase,
  CandlestickChart,
  FileText,
  Home,
  LineChart,
  Pause,
  Play,
  RefreshCw,
  RotateCcw,
  Search,
  Settings,
  Star,
  TrendingDown,
  TrendingUp,
  X,
  Zap,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import styles from "./page.module.css";

type RangeKey = "LIVE" | "1D" | "1W" | "1M" | "1Y" | "5Y" | "ALL";
type ChartType = "candle" | "line";
type MarketScope = "domestic" | "overseas";
type Language = "en" | "ko";
type Signal = "Buy" | "Watch" | "Hold";

type ChartPoint = {
  label: string;
  timestamp?: string;
  value: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

type Stock = {
  symbol: string;
  name: string;
  localName: string;
  market: string;
  region: MarketScope;
  currency: "USD" | "KRW";
  price: number;
  change: number;
  changeAmount?: number;
  open?: number | null;
  high?: number | null;
  low?: number | null;
  volume?: number | null;
  fetchedAt?: string;
  source?: string;
  sector: string;
  sectorKo: string;
  marketCap: number;
  rank: number;
  signal: Signal;
  strategy: string;
  series: Record<RangeKey, ChartPoint[]>;
};

type ThemeUniverse = {
  id: string;
  name: string;
  nameKo: string;
  region: MarketScope;
  description?: string;
  source?: string;
  stocks: Stock[];
};

type ThemeUniverseApiHolding = {
  symbol: string;
  name: string;
  local_name: string;
  market: string;
  region: MarketScope;
  currency: "USD" | "KRW";
  sector: string;
  sector_ko: string;
  market_cap_rank: number;
  market_cap_bucket: "mega-cap" | "large-cap";
};

type ThemeUniverseApiTheme = {
  key: string;
  name: string;
  name_ko?: string;
  description: string;
  sector: string;
  top_market_cap: ThemeUniverseApiHolding[];
};

type ThemeUniverseApiResponse = {
  source: string;
  count: number;
  themes: ThemeUniverseApiTheme[];
  notes: string[];
};

type Position = {
  symbol: string;
  shares: number;
  entryPrice: number;
  entryValue: number;
  entryFee: number;
};

type KisQuote = {
  symbol: string;
  name: string;
  local_name: string;
  market: string;
  region: MarketScope;
  currency: "USD" | "KRW";
  price: number;
  change_amount: number;
  change: number;
  open: number | null;
  high: number | null;
  low: number | null;
  volume: number | null;
  sector: string;
  sector_ko: string;
  source: string;
  fetched_at: string;
};

type KisWatchlistResponse = {
  source: string;
  environment: string;
  count: number;
  data: KisQuote[];
  errors: string[];
};

type KisHistoryCandle = {
  symbol: string;
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number | null;
  source: string;
};

type KisHistoryResponse = {
  source: string;
  environment: string;
  symbol: string;
  range: RangeKey;
  interval: string;
  count: number;
  data: KisHistoryCandle[];
  errors: string[];
};

type DataStatus = "idle" | "loading" | "ready" | "error";

const ranges: RangeKey[] = ["LIVE", "1D", "1W", "1M", "1Y", "5Y", "ALL"];
const initialCash = 10_000_000;
const usdKrw = 1380;
const commissionRate = 0.00015;
const estimatedSlippageRate = 0.0005;
const oneWayTradingCostRate = commissionRate + estimatedSlippageRate;
const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

const copy = {
  en: {
    appName: "Money Copy Bot",
    domestic: "Domestic",
    overseas: "Overseas",
    searchTitle: "Stock search",
    searchPlaceholder: "Search symbol, company, market, or theme",
    language: "Language",
    market: "Market",
    open: "Open",
    dataMode: "Sample universe",
    liveDataMode: "KIS live quotes",
    loadingQuotes: "Loading quotes",
    quoteError: "Quote sync error",
    refreshQuotes: "Refresh quotes",
    updated: "Updated",
    deskMode: "Trading desk",
    rangeMove: "Range move",
    rangeHigh: "High",
    rangeLow: "Low",
    executionMode: "Execution",
    paperOnly: "Paper only",
    signalQueue: "Signal",
    dataBridge: "Data bridge",
    autoTrading: "Auto trading",
    home: "Home",
    portfolio: "Portfolio",
    signals: "Signals",
    automation: "Automation",
    backtest: "Backtest",
    reports: "Reports",
    settings: "Settings",
    broker: "Broker",
    demoAccount: "Paper Account",
    connected: "Connected",
    buyingPower: "Buying Power",
    results: "Results",
    symbols: "symbols",
    watchlist: "Watchlist",
    tracked: "tracked",
    lastPrice: "Last price",
    portfolioSignal: "Portfolio signal",
    sector: "Theme",
    chartRange: "Chart range",
    chartType: "Chart type",
    candle: "Candles",
    line: "Line",
    point: "Point",
    researchNotes: "Theme TOP10",
    portfolioSignalPanel: "Auto strategy",
    sentiment: "Momentum",
    topSignals: "Target TOP3",
    noMatches: "No matching symbols",
    reset: "Reset",
    start: "Run",
    stop: "Pause",
    accountValue: "Account value",
    cash: "Cash",
    pnl: "P/L",
    activeTheme: "Active theme",
    stopLoss: "Stop loss",
    exitRule: "Exit rule",
    rangeLabels: {
      LIVE: "Live",
      "1D": "1D",
      "1W": "1W",
      "1M": "1M",
      "1Y": "1Y",
      "5Y": "5Y",
      ALL: "All",
    },
  },
  ko: {
    appName: "Money Copy Bot",
    domestic: "\uAD6D\uB0B4",
    overseas: "\uD574\uC678",
    searchTitle: "\uC885\uBAA9 \uAC80\uC0C9",
    searchPlaceholder: "\uD2F0\uCEE4, \uD68C\uC0AC, \uC2DC\uC7A5, \uD14C\uB9C8 \uAC80\uC0C9",
    language: "\uC5B8\uC5B4",
    market: "\uC2DC\uC7A5",
    open: "\uAC1C\uC7A5",
    dataMode: "\uC0D8\uD50C \uC720\uB2C8\uBC84\uC2A4",
    liveDataMode: "KIS \uC2E4\uC2DC\uAC04 \uC2DC\uC138",
    loadingQuotes: "\uC2DC\uC138 \uBD88\uB7EC\uC624\uB294 \uC911",
    quoteError: "\uC2DC\uC138 \uC5F0\uB3D9 \uC624\uB958",
    refreshQuotes: "\uC2DC\uC138 \uC0C8\uB85C\uACE0\uCE68",
    updated: "\uAC31\uC2E0",
    deskMode: "\uD2B8\uB808\uC774\uB529 \uB370\uC2A4\uD06C",
    rangeMove: "\uAE30\uAC04 \uB4F1\uB77D",
    rangeHigh: "\uACE0\uAC00",
    rangeLow: "\uC800\uAC00",
    executionMode: "\uC2E4\uD589",
    paperOnly: "\uBAA8\uC758",
    signalQueue: "\uC2DC\uADF8\uB110",
    dataBridge: "\uB370\uC774\uD130 \uBE0C\uB9AC\uC9C0",
    autoTrading: "\uC790\uB3D9 \uB2E8\uD0C0",
    home: "\uD648",
    portfolio: "\uD3EC\uD2B8\uD3F4\uB9AC\uC624",
    signals: "\uC2DC\uADF8\uB110",
    automation: "\uC790\uB3D9\uD654",
    backtest: "\uBC31\uD14C\uC2A4\uD2B8",
    reports: "\uB9AC\uD3EC\uD2B8",
    settings: "\uC124\uC815",
    broker: "\uC99D\uAD8C\uC0AC",
    demoAccount: "\uBAA8\uC758 \uACC4\uC88C",
    connected: "\uC5F0\uACB0\uB428",
    buyingPower: "\uB9E4\uC218 \uAC00\uB2A5\uAE08",
    results: "\uAC80\uC0C9 \uACB0\uACFC",
    symbols: "\uC885\uBAA9",
    watchlist: "\uAD00\uC2EC\uC885\uBAA9",
    tracked: "\uCD94\uC801",
    lastPrice: "\uD604\uC7AC\uAC00",
    portfolioSignal: "\uD3EC\uD2B8\uD3F4\uB9AC\uC624 \uC2DC\uADF8\uB110",
    sector: "\uD14C\uB9C8",
    chartRange: "\uCC28\uD2B8 \uAE30\uAC04",
    chartType: "\uCC28\uD2B8 \uC720\uD615",
    candle: "\uBD09\uCC28\uD2B8",
    line: "\uC120\uCC28\uD2B8",
    point: "\uC9C0\uC810",
    researchNotes: "\uD14C\uB9C8 TOP10",
    portfolioSignalPanel: "\uC790\uB3D9\uB9E4\uB9E4 \uC804\uB7B5",
    sentiment: "\uBAA8\uBA58\uD140",
    topSignals: "\uD22C\uC790 TOP3",
    noMatches: "\uAC80\uC0C9 \uACB0\uACFC \uC5C6\uC74C",
    reset: "\uCD08\uAE30\uD654",
    start: "\uC2E4\uD589",
    stop: "\uC77C\uC2DC\uC815\uC9C0",
    accountValue: "\uCD1D \uD3C9\uAC00",
    cash: "\uD604\uAE08",
    pnl: "\uC218\uC775",
    activeTheme: "\uC120\uD0DD \uD14C\uB9C8",
    stopLoss: "2% \uC190\uC808",
    exitRule: "\uC774\uD3C9 \uAEBC\uC9D0/\uC7A5\uB9C8\uAC10 5\uBD84",
    rangeLabels: {
      LIVE: "\uC2E4\uC2DC\uAC04",
      "1D": "1D",
      "1W": "1W",
      "1M": "1M",
      "1Y": "1Y",
      "5Y": "5Y",
      ALL: "\uC804\uCCB4",
    },
  },
} as const;

const themeSeed = [
  {
    id: "ai-semi",
    name: "AI Semiconductors",
    nameKo: "AI \uBC18\uB3C4\uCCB4",
    region: "overseas" as const,
    stocks: [
      ["NVDA", "NVIDIA Corp.", "\uC5D4\uBE44\uB514\uC544", "NASDAQ", 214.75, 2.18, 5_280_000],
      ["AVGO", "Broadcom Inc.", "\uBE0C\uB85C\uB4DC\uCEF4", "NASDAQ", 1812.4, 1.24, 745_000],
      ["AMD", "Advanced Micro Devices", "AMD", "NASDAQ", 168.22, 0.82, 274_000],
      ["TSM", "Taiwan Semiconductor", "TSMC", "NYSE", 247.91, 1.38, 1_285_000],
      ["ASML", "ASML Holding", "ASML", "NASDAQ", 1028.3, 0.44, 405_000],
      ["QCOM", "Qualcomm Inc.", "\uD000\uCEF4", "NASDAQ", 183.18, -0.28, 204_000],
      ["AMAT", "Applied Materials", "\uC5B4\uD50C\uB77C\uC774\uB4DC", "NASDAQ", 221.14, 0.67, 188_000],
      ["LRCX", "Lam Research", "\uB7A8\uB9AC\uC11C\uCE58", "NASDAQ", 967.2, 0.58, 122_000],
      ["MU", "Micron Technology", "\uB9C8\uC774\uD06C\uB860", "NASDAQ", 107.96, 1.45, 119_000],
      ["ARM", "Arm Holdings", "\uC554", "NASDAQ", 142.63, 0.96, 132_000],
    ],
  },
  {
    id: "us-platform",
    name: "Platform Giants",
    nameKo: "\uD50C\uB7AB\uD3FC \uBE45\uD14C\uD06C",
    region: "overseas" as const,
    stocks: [
      ["MSFT", "Microsoft", "\uB9C8\uC774\uD06C\uB85C\uC18C\uD504\uD2B8", "NASDAQ", 472.11, 0.72, 3_510_000],
      ["AAPL", "Apple Inc.", "\uC560\uD50C", "NASDAQ", 203.41, -0.16, 3_125_000],
      ["GOOGL", "Alphabet Class A", "\uC54C\uD30C\uBCB3", "NASDAQ", 182.34, 0.48, 2_245_000],
      ["AMZN", "Amazon.com", "\uC544\uB9C8\uC874", "NASDAQ", 193.42, 0.56, 2_010_000],
      ["META", "Meta Platforms", "\uBA54\uD0C0", "NASDAQ", 486.72, 1.04, 1_220_000],
      ["NFLX", "Netflix", "\uB137\uD50C\uB9AD\uC2A4", "NASDAQ", 706.1, 0.31, 302_000],
      ["ORCL", "Oracle", "\uC624\uB77C\uD074", "NYSE", 141.62, 0.22, 390_000],
      ["CRM", "Salesforce", "\uC138\uC77C\uC988\uD3EC\uC2A4", "NYSE", 251.82, -0.51, 244_000],
      ["ADBE", "Adobe", "\uC5B4\uB3C4\uBE44", "NASDAQ", 526.38, 0.39, 236_000],
      ["NOW", "ServiceNow", "\uC11C\uBE44\uC2A4\uB098\uC6B0", "NYSE", 781.2, 0.77, 161_000],
    ],
  },
  {
    id: "k-semi",
    name: "Korea Semiconductors",
    nameKo: "\uAD6D\uB0B4 \uBC18\uB3C4\uCCB4",
    region: "domestic" as const,
    stocks: [
      ["005930", "Samsung Electronics", "\uC0BC\uC131\uC804\uC790", "KOSPI", 73500, 0.68, 4_385_000],
      ["000660", "SK Hynix", "SK\uD558\uC774\uB2C9\uC2A4", "KOSPI", 229300, 1.94, 1_670_000],
      ["042700", "Hanmi Semiconductor", "\uD55C\uBBF8\uBC18\uB3C4\uCCB4", "KOSPI", 151200, 2.36, 95_000],
      ["058470", "Leeno Industrial", "\uB9AC\uB178\uACF5\uC5C5", "KOSDAQ", 214500, 1.08, 62_000],
      ["403870", "HPSP", "HPSP", "KOSDAQ", 38450, 0.83, 52_000],
      ["039030", "EO Technics", "\uC774\uC624\uD14C\uD06C\uB2C9\uC2A4", "KOSDAQ", 183000, -0.42, 36_000],
      ["240810", "Wonik IPS", "\uC6D0\uC775IPS", "KOSDAQ", 39750, 0.64, 31_000],
      ["108320", "LX Semicon", "LX\uC138\uBBF8\uCF58", "KOSPI", 80300, -0.21, 27_000],
      ["095340", "ISC", "ISC", "KOSDAQ", 74200, 0.91, 26_000],
      ["036930", "Jusung Engineering", "\uC8FC\uC131\uC5D4\uC9C0\uB2C8\uC5B4\uB9C1", "KOSDAQ", 33550, 1.31, 24_000],
    ],
  },
  {
    id: "k-battery",
    name: "Korea Batteries",
    nameKo: "\uAD6D\uB0B4 2\uCC28\uC804\uC9C0",
    region: "domestic" as const,
    stocks: [
      ["373220", "LG Energy Solution", "LG\uC5D0\uB108\uC9C0\uC194\uB8E8\uC158", "KOSPI", 356000, 0.54, 833_000],
      ["006400", "Samsung SDI", "\uC0BC\uC131SDI", "KOSPI", 421000, 0.78, 289_000],
      ["051910", "LG Chem", "LG\uD654\uD559", "KOSPI", 392500, -0.19, 277_000],
      ["247540", "EcoPro BM", "\uC5D0\uCF54\uD504\uB85CBM", "KOSDAQ", 213500, 1.66, 228_000],
      ["086520", "EcoPro", "\uC5D0\uCF54\uD504\uB85C", "KOSDAQ", 97200, 1.12, 129_000],
      ["003670", "Posco Future M", "\uD3EC\uC2A4\uCF54\uD4E8\uCC98\uC5E0", "KOSPI", 257000, 0.47, 111_000],
      ["066970", "L&F", "\uC5D8\uC564\uC5D0\uD504", "KOSDAQ", 143800, -0.36, 46_000],
      ["278280", "Chunbo", "\uCC9C\uBCF4", "KOSDAQ", 89400, 0.28, 17_000],
      ["005070", "Cosmo AM&T", "\uCF54\uC2A4\uBAA8\uC2E0\uC18C\uC7AC", "KOSPI", 125600, 0.71, 29_000],
      ["096770", "SK Innovation", "SK\uC774\uB178\uBCA0\uC774\uC158", "KOSPI", 118400, -0.43, 109_000],
    ],
  },
] as const;

function formatClock(totalMinutes: number) {
  const hours = Math.floor(totalMinutes / 60);
  const minutes = Math.round(totalMinutes % 60);

  return `${hours.toString().padStart(2, "0")}:${minutes.toString().padStart(2, "0")}`;
}

function pointLabel(range: RangeKey, index: number, count: number) {
  if (range === "LIVE" || range === "1D") {
    const start = 9 * 60;
    const end = 15 * 60 + 30;
    return formatClock(start + ((end - start) * index) / Math.max(count - 1, 1));
  }

  if (range === "1W") {
    return ["Mon", "Tue", "Wed", "Thu", "Fri"][Math.min(4, Math.floor((index / count) * 5))];
  }

  if (range === "1M") {
    return `D-${count - index - 1}`;
  }

  if (range === "1Y") {
    return `M-${Math.max(0, Math.ceil(((count - index - 1) / count) * 12))}`;
  }

  if (range === "5Y") {
    return `Y-${Math.max(0, Math.ceil(((count - index - 1) / count) * 5))}`;
  }

  return `P-${index + 1}`;
}

function pointsForRange(range: RangeKey) {
  return {
    LIVE: 84,
    "1D": 96,
    "1W": 70,
    "1M": 88,
    "1Y": 96,
    "5Y": 110,
    ALL: 132,
  }[range];
}

function buildSeries(price: number, change: number, seed: number): Record<RangeKey, ChartPoint[]> {
  return Object.fromEntries(
    ranges.map((range) => {
      const count = pointsForRange(range);
      const rangeBias = { LIVE: 0.18, "1D": 0.5, "1W": 1.4, "1M": 2.8, "1Y": 8.2, "5Y": 24, ALL: 38 }[
        range
      ];
      const start = price / (1 + (change * rangeBias) / 100);
      const spread = Math.max(price * 0.006, Math.abs(price - start) * 0.36, 1);
      const points = Array.from({ length: count }, (_, index) => {
        const ratio = index / Math.max(count - 1, 1);
        const trend = start + (price - start) * ratio;
        const cycle = Math.sin(index * 0.34 + seed) * spread + Math.sin(index * 0.09 + seed * 0.7) * spread * 0.55;
        const close = index === count - 1 ? price : Math.max(1, trend + cycle);
        const open = index === 0 ? close - spread * 0.16 : Math.max(1, trend - cycle * 0.22);
        const wick = Math.max(Math.abs(close - open) * 0.62, spread * 0.42);

        return {
          label: pointLabel(range, index, count),
          value: close,
          open,
          high: Math.max(open, close) + wick,
          low: Math.max(0.01, Math.min(open, close) - wick),
          close,
          volume: Math.round(250000 + Math.abs(Math.sin(index + seed)) * 2200000),
        };
      });

      return [range, points];
    }),
  ) as Record<RangeKey, ChartPoint[]>;
}

function buildUniverse(): ThemeUniverse[] {
  return themeSeed.map((theme) => ({
    ...theme,
    stocks: theme.stocks.map((row, index) => {
      const [symbol, name, localName, market, price, change, marketCap] = row;
      const currency = theme.region === "domestic" ? "KRW" : "USD";
      const numericPrice = Number(price);
      const numericChange = Number(change);

      return {
        symbol: String(symbol),
        name: String(name),
        localName: String(localName),
        market: String(market),
        region: theme.region,
        currency,
        price: numericPrice,
        change: numericChange,
        changeAmount: numericPrice * (numericChange / 100),
        open: numericPrice / (1 + numericChange / 100),
        high: numericPrice * 1.012,
        low: numericPrice * 0.988,
        volume: 900000 + index * 117000,
        sector: theme.name,
        sectorKo: theme.nameKo,
        marketCap: Number(marketCap),
        rank: index + 1,
        signal: numericChange >= 1 ? "Buy" : numericChange < 0 ? "Watch" : "Hold",
        strategy: index < 3 ? "Theme rotation TOP3" : "Theme watchlist TOP10",
        series: buildSeries(numericPrice, numericChange, index + theme.id.length),
      };
    }),
  }));
}

function stockFallbackPrice(symbol: string, region: MarketScope, rank: number) {
  const fallbackStock = buildUniverse()
    .flatMap((theme) => theme.stocks)
    .find((stock) => stock.symbol === symbol);

  if (fallbackStock) {
    return {
      price: fallbackStock.price,
      change: fallbackStock.change,
      marketCap: fallbackStock.marketCap,
    };
  }

  const price = region === "domestic" ? 18000 + rank * 26500 : 48 + rank * 37;

  return {
    price,
    change: 0.3 + (rank % 4) * 0.34,
    marketCap: region === "domestic" ? 900000 - rank * 56000 : 2200000 - rank * 128000,
  };
}

function universeFromApi(payload: ThemeUniverseApiResponse): ThemeUniverse[] {
  if (!payload.themes.length) {
    return buildUniverse();
  }

  return payload.themes.map((theme) => ({
    id: theme.key,
    name: theme.name,
    nameKo: theme.name_ko ?? theme.name,
    description: theme.description,
    region: theme.top_market_cap[0]?.region ?? "overseas",
    source: payload.source,
    stocks: theme.top_market_cap.map((holding) => {
      const fallback = stockFallbackPrice(holding.symbol, holding.region, holding.market_cap_rank);
      const price = fallback.price;
      const change = fallback.change;

      return {
        symbol: holding.symbol,
        name: holding.name,
        localName: holding.local_name,
        market: holding.market,
        region: holding.region,
        currency: holding.currency,
        price,
        change,
        changeAmount: price * (change / 100),
        open: price / (1 + change / 100),
        high: price * 1.012,
        low: price * 0.988,
        volume: 900000 + holding.market_cap_rank * 117000,
        sector: holding.sector,
        sectorKo: holding.sector_ko,
        marketCap: fallback.marketCap,
        rank: holding.market_cap_rank,
        signal: stockSignal(change),
        strategy: holding.market_cap_rank <= 3 ? "API theme rotation TOP3" : "API theme TOP10",
        series: buildSeries(price, change, holding.market_cap_rank + theme.key.length),
      };
    }),
  }));
}

function stockSignal(change: number): Signal {
  if (change >= 1) {
    return "Buy";
  }

  if (change < 0) {
    return "Watch";
  }

  return "Hold";
}

function pointFromHistoryCandle(candle: KisHistoryCandle): ChartPoint {
  return {
    label: candle.timestamp,
    timestamp: candle.timestamp,
    value: candle.close,
    open: candle.open,
    high: candle.high,
    low: candle.low,
    close: candle.close,
    volume: candle.volume ?? 0,
  };
}

function formatChartPointLabel(point: ChartPoint, range: RangeKey, language: Language) {
  if (!point.timestamp) {
    return point.label;
  }

  const date = new Date(point.timestamp);

  if (Number.isNaN(date.getTime())) {
    return point.label;
  }

  const locale = language === "ko" ? "ko-KR" : "en-US";

  if (range === "LIVE" || range === "1D") {
    return new Intl.DateTimeFormat(locale, { hour: "2-digit", minute: "2-digit" }).format(date);
  }

  return new Intl.DateTimeFormat(locale, { month: "short", day: "2-digit" }).format(date);
}

function stockName(stock: Stock, language: Language) {
  return language === "ko" ? stock.localName : stock.name;
}

function sectorName(stock: Stock, language: Language) {
  return language === "ko" ? stock.sectorKo : stock.sector;
}

function themeName(theme: ThemeUniverse, language: Language) {
  return language === "ko" ? theme.nameKo : theme.name;
}

function signalLabel(signal: Signal, language: Language) {
  if (language === "en") {
    return signal;
  }

  return { Buy: "\uB9E4\uC218", Watch: "\uAD00\uCC30", Hold: "\uBCF4\uC720" }[signal];
}

function formatMoney(value: number, currency: "KRW" | "USD" = "KRW") {
  if (currency === "USD") {
    return `$${value.toLocaleString("en-US", { maximumFractionDigits: 2, minimumFractionDigits: 2 })}`;
  }

  return `${Math.round(value).toLocaleString("ko-KR")}\uC6D0`;
}

function formatPrice(stock: Stock) {
  return stock.currency === "KRW" ? formatMoney(stock.price) : formatMoney(stock.price, "USD");
}

function priceToKrw(stock: Stock) {
  return stock.currency === "KRW" ? stock.price : stock.price * usdKrw;
}

function liquidationValue(position: Position, stock: Stock | undefined) {
  if (!stock) {
    return 0;
  }

  return position.shares * priceToKrw(stock) * (1 - oneWayTradingCostRate);
}

function formatCompactNumber(value: number | null | undefined) {
  if (!value) {
    return "-";
  }

  return value.toLocaleString("ko-KR", { maximumFractionDigits: 0 });
}

function formatFetchedAt(value: string | undefined, language: Language) {
  if (!value) {
    return "-";
  }

  return new Intl.DateTimeFormat(language === "ko" ? "ko-KR" : "en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));
}

function movingAverage(points: ChartPoint[], windowSize: number) {
  const slice = points.slice(-windowSize);
  return slice.reduce((sum, point) => sum + point.close, 0) / Math.max(slice.length, 1);
}

function stockMovingAverageTrend(stock: Stock) {
  const points = stock.series.LIVE;
  const fast = movingAverage(points, 8);
  const previousFast = movingAverage(points.slice(0, -4), 8);
  const slow = movingAverage(points, 26);
  const fastSpread = ((fast - slow) / slow) * 100;
  const slope = ((fast - previousFast) / previousFast) * 100;

  return {
    fast,
    previousFast,
    slow,
    rising: fast > previousFast && fast > slow,
    score: fastSpread + slope * 2,
  };
}

function momentumScore(stock: Stock) {
  const trend = stockMovingAverageTrend(stock);

  return trend.rising ? trend.score + stock.change * 0.2 : trend.score * 0.35;
}

function themeMomentum(theme: ThemeUniverse) {
  return theme.stocks.slice(0, 10).reduce((sum, stock) => sum + momentumScore(stock), 0) / 10;
}

function isMovingAverageRollingOver(theme: ThemeUniverse) {
  const lastThree = theme.stocks.slice(0, 10).map((stock) => {
    const trend = stockMovingAverageTrend(stock);

    return trend.fast < trend.previousFast || trend.fast < trend.slow;
  });

  return lastThree.filter(Boolean).length >= 6;
}

function themeSparklinePath(theme: ThemeUniverse, width = 142, height = 34) {
  const points = theme.stocks.slice(0, 10).map((stock) => momentumScore(stock));
  const min = Math.min(...points);
  const max = Math.max(...points);
  const spread = max - min || 1;

  return points
    .map((value, index) => {
      const x = (index / Math.max(points.length - 1, 1)) * width;
      const y = height - ((value - min) / spread) * height;

      return `${index === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");
}

function xFor(index: number, count: number, width: number, paddingLeft: number, paddingRight: number) {
  return paddingLeft + (index / Math.max(count - 1, 1)) * (width - paddingLeft - paddingRight);
}

function yFor(value: number, min: number, max: number, height: number, paddingTop: number, paddingBottom: number) {
  const spread = max - min || 1;
  return paddingTop + ((max - value) / spread) * (height - paddingTop - paddingBottom);
}

function buildPath(points: ChartPoint[], width: number, height: number, min: number, max: number) {
  return points
    .map((point, index) => {
      const x = xFor(index, points.length, width, 60, 26);
      const y = yFor(point.value, min, max, height, 20, 52);
      return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
}

function axisTickIndexes(count: number) {
  const tickCount = 6;
  const step = Math.max(1, Math.floor((count - 1) / (tickCount - 1)));
  return [...new Set(Array.from({ length: tickCount }, (_, index) => Math.min(count - 1, index * step)).concat(count - 1))];
}

function mergeLiveQuotes(universes: ThemeUniverse[], quotes: KisQuote[]) {
  if (!quotes.length) {
    return universes;
  }

  const quoteMap = new Map(quotes.map((quote) => [quote.symbol, quote]));

  return universes.map((theme) => ({
    ...theme,
    stocks: theme.stocks.map((stock) => {
      const quote = quoteMap.get(stock.symbol);

      if (!quote) {
        return stock;
      }

      return {
        ...stock,
        name: quote.name,
        localName: quote.local_name,
        market: quote.market,
        price: quote.price,
        change: quote.change,
        changeAmount: quote.change_amount,
        open: quote.open,
        high: quote.high,
        low: quote.low,
        volume: quote.volume,
        fetchedAt: quote.fetched_at,
        source: quote.source,
        signal: stockSignal(quote.change),
        strategy: "KIS quote + theme rotation",
        series: buildSeries(quote.price, quote.change, stock.rank + theme.id.length),
      };
    }),
  }));
}

function tickUniverses(universes: ThemeUniverse[], tick: number) {
  return universes.map((theme, themeIndex) => ({
    ...theme,
    stocks: theme.stocks.map((stock, stockIndex) => {
      const drift = Math.sin((tick + stockIndex * 11 + themeIndex * 17) / 17) * 0.0008 + momentumScore(stock) * 0.000025;
      const nextPrice = Math.max(1, stock.price * (1 + drift));
      const previousClose = stock.series.LIVE.at(-1)?.close ?? stock.price;
      const nextPoint: ChartPoint = {
        label: formatClock(9 * 60 + ((tick + stockIndex * 3) % 390)),
        value: nextPrice,
        open: previousClose,
        high: Math.max(previousClose, nextPrice) * 1.0014,
        low: Math.min(previousClose, nextPrice) * 0.9986,
        close: nextPrice,
        volume: Math.round((stock.volume ?? 400000) * (0.7 + Math.abs(Math.sin(tick / 9 + stockIndex)))),
      };
      const live = [...stock.series.LIVE.slice(-83), nextPoint];
      const change = ((nextPrice - (stock.open || nextPrice)) / (stock.open || nextPrice)) * 100;

      return {
        ...stock,
        price: nextPrice,
        change,
        changeAmount: nextPrice - (stock.open || nextPrice),
        high: Math.max(stock.high ?? nextPrice, nextPrice),
        low: Math.min(stock.low ?? nextPrice, nextPrice),
        signal: stockSignal(change),
        series: { ...stock.series, LIVE: live, "1D": [...stock.series["1D"].slice(-95), nextPoint] },
      };
    }),
  }));
}

export default function StockDashboard() {
  const [query, setQuery] = useState("");
  const [marketScope, setMarketScope] = useState<MarketScope>("domestic");
  const [language, setLanguage] = useState<Language>("ko");
  const [selectedSymbol, setSelectedSymbol] = useState("005930");
  const [watchlist, setWatchlist] = useState(["005930", "000660", "373220", "NVDA", "MSFT"]);
  const [range, setRange] = useState<RangeKey>("LIVE");
  const [chartType, setChartType] = useState<ChartType>("candle");
  const [activePoint, setActivePoint] = useState<number | null>(null);
  const [universes, setUniverses] = useState<ThemeUniverse[]>(() => buildUniverse());
  const [chartHistory, setChartHistory] = useState<Record<string, Partial<Record<RangeKey, ChartPoint[]>>>>({});
  const [dataStatus, setDataStatus] = useState<DataStatus>("idle");
  const [dataError, setDataError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const [autoRun, setAutoRun] = useState(true);
  const [cash, setCash] = useState(initialCash);
  const [positions, setPositions] = useState<Position[]>([]);
  const [tradeLog, setTradeLog] = useState<string[]>(["Ready: 10,000,000 KRW paper account"]);
  const [tick, setTick] = useState(0);
  const [activeNav, setActiveNav] = useState("home");
  const [statusMessage, setStatusMessage] = useState("자동 전략 대기 중");

  const t = copy[language];
  const stocks = useMemo(() => universes.flatMap((theme) => theme.stocks), [universes]);
  const marketThemes = useMemo(() => universes.filter((theme) => theme.region === marketScope), [marketScope, universes]);
  const activeTheme = useMemo(
    () => [...marketThemes].sort((a, b) => themeMomentum(b) - themeMomentum(a))[0],
    [marketThemes],
  );
  const targetStocks = useMemo(() => activeTheme?.stocks.slice(0, 3) ?? [], [activeTheme]);
  const marketStocks = useMemo(
    () => marketThemes.flatMap((theme) => theme.stocks).sort((a, b) => b.marketCap - a.marketCap),
    [marketThemes],
  );
  const filteredStocks = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();

    if (!normalizedQuery) {
      return marketStocks;
    }

    return marketStocks.filter((stock) =>
      [stock.symbol, stock.name, stock.localName, stock.market, stock.sector, stock.sectorKo].some((value) =>
        value.toLowerCase().includes(normalizedQuery),
      ),
    );
  }, [marketStocks, query]);
  const selectedStock =
    stocks.find((stock) => stock.symbol === selectedSymbol && stock.region === marketScope) ??
    marketStocks[0] ??
    stocks[0];

  useEffect(() => {
    const controller = new AbortController();

    async function loadThemeUniverse() {
      try {
        const response = await fetch(`${apiBaseUrl}/universe/themes`, { signal: controller.signal });

        if (!response.ok) {
          return;
        }

        const payload = (await response.json()) as ThemeUniverseApiResponse;
        const nextUniverses = universeFromApi(payload);

        if (!nextUniverses.length) {
          return;
        }

        setUniverses(nextUniverses);
      } catch {
        return;
      }
    }

    loadThemeUniverse();

    return () => controller.abort();
  }, []);

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      setTick((currentTick) => {
        const nextTick = currentTick + 1;
        setUniverses((currentUniverses) => tickUniverses(currentUniverses, nextTick));

        return nextTick;
      });
    }, 1000);

    return () => window.clearInterval(intervalId);
  }, []);

  useEffect(() => {
    const controller = new AbortController();

    async function loadQuotes() {
      setDataStatus((currentStatus) => (currentStatus === "idle" ? "loading" : currentStatus));
      setDataError("");

      try {
        const response = await fetch(`${apiBaseUrl}/quotes/kis/watchlist`, { signal: controller.signal });

        if (!response.ok) {
          const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
          throw new Error(payload?.detail ?? `KIS quote request failed: ${response.status}`);
        }

        const payload = (await response.json()) as KisWatchlistResponse;
        setUniverses((currentUniverses) => mergeLiveQuotes(currentUniverses, payload.data));
        setDataStatus(payload.errors.length ? "error" : "ready");
        setDataError(payload.errors.join(" / "));
      } catch (error) {
        if (controller.signal.aborted) {
          return;
        }

        setDataStatus("error");
        setDataError(error instanceof Error ? error.message : "KIS quote request failed.");
      }
    }

    loadQuotes();
    const intervalId = window.setInterval(loadQuotes, 1000);

    return () => {
      controller.abort();
      window.clearInterval(intervalId);
    };
  }, [refreshKey]);

  useEffect(() => {
    if (!selectedStock) {
      return;
    }

    const controller = new AbortController();

    async function loadChartHistory() {
      try {
        const response = await fetch(`${apiBaseUrl}/quotes/kis/history/${selectedStock.symbol}?range=${range}`, {
          signal: controller.signal,
        });

        if (!response.ok) {
          return;
        }

        const payload = (await response.json()) as KisHistoryResponse;
        const points = payload.data.map(pointFromHistoryCandle);

        if (!points.length) {
          return;
        }

        setChartHistory((currentHistory) => ({
          ...currentHistory,
          [selectedStock.symbol]: {
            ...currentHistory[selectedStock.symbol],
            [range]: points,
          },
        }));
      } catch {
        return;
      }
    }

    loadChartHistory();
    const intervalId = range === "LIVE" || range === "1D" ? window.setInterval(loadChartHistory, 1000) : null;

    return () => {
      controller.abort();
      if (intervalId) {
        window.clearInterval(intervalId);
      }
    };
  }, [range, selectedStock]);

  useEffect(() => {
    if (!autoRun || !activeTheme || !targetStocks.length) {
      return;
    }

    const timeoutId = window.setTimeout(() => {
      const portfolioValue = positions.reduce((sum, position) => {
        const stock = stocks.find((item) => item.symbol === position.symbol);
        return sum + liquidationValue(position, stock);
      }, cash);
      const lossTriggered = positions.some((position) => {
        const stock = stocks.find((item) => item.symbol === position.symbol);
        return stock ? liquidationValue(position, stock) <= position.entryValue * 0.98 : false;
      });
      const tradingDaySeconds = 390 * 60;
      const closeWindowSeconds = 5 * 60;
      const isCloseWindow = tick % tradingDaySeconds >= tradingDaySeconds - closeWindowSeconds;
      const maRollingOver = isMovingAverageRollingOver(activeTheme);
      const shouldExit = lossTriggered || maRollingOver || isCloseWindow;
      const canEnter = !maRollingOver && !isCloseWindow;
      const currentSymbols = positions.map((position) => position.symbol).sort().join(",");
      const targetSymbols = targetStocks.map((stock) => stock.symbol).sort().join(",");

      if (positions.length && (shouldExit || currentSymbols !== targetSymbols)) {
        setCash(portfolioValue);
        setPositions([]);
        setTradeLog((log) => [
          `${new Date().toLocaleTimeString("ko-KR")} SELL ${
            lossTriggered ? "stop-loss" : isCloseWindow ? "pre-close" : maRollingOver ? "MA rollover" : "rotation"
          } ${formatMoney(portfolioValue)} net of fees`,
          ...log.slice(0, 5),
        ]);
        setStatusMessage(lossTriggered ? "2% 손절 매도 실행" : isCloseWindow ? "장마감 5분 전 청산" : "이동평균 꺾임 매도");
        return;
      }

      if (!positions.length && cash > 1000 && canEnter) {
        const allocation = cash / targetStocks.length;
        const nextPositions = targetStocks.map((stock) => {
          const entryPrice = priceToKrw(stock);
          const effectiveEntryPrice = entryPrice * (1 + oneWayTradingCostRate);

          return {
            symbol: stock.symbol,
            shares: allocation / effectiveEntryPrice,
            entryPrice,
            entryValue: allocation,
            entryFee: allocation * oneWayTradingCostRate,
          };
        });

        setCash(0);
        setPositions(nextPositions);
        setTradeLog((log) => [
          `${new Date().toLocaleTimeString("ko-KR")} BUY ${themeName(activeTheme, language)} TOP3 fee ${formatMoney(
            cash * oneWayTradingCostRate,
          )}`,
          ...log.slice(0, 5),
        ]);
        setStatusMessage(`${themeName(activeTheme, language)} TOP3 자동 진입`);
        return;
      }

      if (!positions.length && cash > 1000 && !canEnter) {
        setStatusMessage(maRollingOver ? "이동평균 회복 대기 중" : "장마감 5분 전 신규 진입 중지");
      }
    }, 0);

    return () => window.clearTimeout(timeoutId);
  }, [activeTheme, autoRun, cash, language, positions, stocks, targetStocks, tick]);

  const selectedHistoryPoints = chartHistory[selectedStock.symbol]?.[range];
  const selectedPoints = selectedHistoryPoints?.length ? selectedHistoryPoints : selectedStock.series[range];
  const selectedValues = selectedPoints.map((point) => point.value);
  const selectedIndex = Math.min(activePoint ?? selectedPoints.length - 1, selectedPoints.length - 1);
  const selectedPoint = selectedPoints[selectedIndex];
  const rangeStart = selectedValues[0];
  const rangeEnd = selectedValues[selectedValues.length - 1];
  const rangeMove = ((rangeEnd - rangeStart) / rangeStart) * 100;
  const chartWidth = 900;
  const chartHeight = 420;
  const candleExtremes = selectedPoints.flatMap((point) => [point.high, point.low]);
  const rawChartMin = Math.min(...selectedValues, ...candleExtremes);
  const rawChartMax = Math.max(...selectedValues, ...candleExtremes);
  const chartSpread = rawChartMax - rawChartMin || Math.abs(rangeEnd) * 0.01 || 1;
  const chartMin = rawChartMin - chartSpread * 0.12;
  const chartMax = rawChartMax + chartSpread * 0.1;
  const path = buildPath(selectedPoints, chartWidth, chartHeight, chartMin, chartMax);
  const xAxisIndexes = axisTickIndexes(selectedPoints.length);
  const yAxisTicks = [0, 1, 2, 3, 4].map((item) => chartMax - ((chartMax - chartMin) * item) / 4);
  const candleWidth = Math.max(3, Math.min(10, ((chartWidth - 86) / selectedPoints.length) * 0.55));
  const activeX = xFor(selectedIndex, selectedPoints.length, chartWidth, 60, 26);
  const activeY = yFor(selectedPoint.value, chartMin, chartMax, chartHeight, 20, 52);
  const volumeMax = Math.max(...selectedPoints.map((point) => point.volume || 1));
  const watchedStocks = watchlist
    .map((symbol) => stocks.find((stock) => stock.symbol === symbol))
    .filter((stock): stock is Stock => Boolean(stock))
    .filter((stock) => stock.region === marketScope);
  const latestFetchedAt = stocks.find((stock) => stock.fetchedAt)?.fetchedAt;
  const accountValue = positions.reduce((sum, position) => {
    const stock = stocks.find((item) => item.symbol === position.symbol);
    return sum + liquidationValue(position, stock);
  }, cash);
  const pnl = accountValue - initialCash;
  const pnlRate = (pnl / initialCash) * 100;
  const dataModeLabel =
    dataStatus === "loading"
      ? t.loadingQuotes
      : dataStatus === "error"
        ? t.quoteError
        : stocks.some((stock) => stock.source)
          ? t.liveDataMode
          : t.dataMode;
  const marketFeed = [
    {
      label: "KIS",
      value: stocks.some((stock) => stock.source) ? "1s synced" : "1s simulated",
      change: dataStatus === "error" ? "ERR" : "LIVE",
      positive: dataStatus !== "error",
    },
    {
      label: activeTheme ? themeName(activeTheme, language) : "-",
      value: `${(activeTheme ? themeMomentum(activeTheme) : 0).toFixed(2)} MA`,
      change: t.activeTheme,
      positive: true,
    },
    {
      label: t.accountValue,
      value: formatMoney(accountValue),
      change: `${pnl >= 0 ? "+" : ""}${pnlRate.toFixed(2)}%`,
      positive: pnl >= 0,
    },
  ];
  const navItems = [
    { id: "home", label: t.home, icon: Home },
    { id: "portfolio", label: t.portfolio, icon: Briefcase },
    { id: "signals", label: t.signals, icon: BarChart3 },
    { id: "automation", label: t.automation, icon: Zap },
    { id: "backtest", label: t.backtest, icon: LineChart },
    { id: "reports", label: t.reports, icon: FileText },
    { id: "settings", label: t.settings, icon: Settings },
  ];

  function selectMarket(nextScope: MarketScope) {
    const firstStock = stocks.find((stock) => stock.region === nextScope);

    setMarketScope(nextScope);
    setSelectedSymbol(firstStock?.symbol ?? selectedSymbol);
    setQuery("");
    setActivePoint(null);
  }

  function toggleWatchlist(symbol: string) {
    setWatchlist((currentWatchlist) =>
      currentWatchlist.includes(symbol)
        ? currentWatchlist.filter((watchSymbol) => watchSymbol !== symbol)
        : [...currentWatchlist, symbol],
    );
  }

  function resetSimulation() {
    setCash(initialCash);
    setPositions([]);
    setTradeLog(["Reset: 10,000,000 KRW paper account"]);
    setStatusMessage("모의 계좌를 10,000,000원으로 초기화");
  }

  function focusTheme(theme: ThemeUniverse) {
    const firstStock = theme.stocks[0];

    if (!firstStock) {
      return;
    }

    setMarketScope(theme.region);
    setSelectedSymbol(firstStock.symbol);
    setQuery("");
    setActivePoint(null);
    setStatusMessage(`${themeName(theme, language)} TOP10 그래프 확인`);
  }

  function handleChartPointerMove(event: React.PointerEvent<SVGSVGElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    const relativeX = event.clientX - rect.left;
    const ratio = Math.min(Math.max(relativeX / rect.width, 0), 1);
    setActivePoint(Math.round(ratio * (selectedPoints.length - 1)));
  }

  return (
    <main className={styles.appShell}>
      <aside className={styles.sidebar} aria-label="MCBot navigation">
        <div className={styles.brandBlock}>
          <div className={styles.brandMark}>MC</div>
          <div>
            <strong>MCBot</strong>
            <span>{t.appName}</span>
          </div>
        </div>
        <nav className={styles.navList}>
          {navItems.map((item) => {
            const Icon = item.icon;

            return (
              <button
                className={item.id === activeNav ? styles.navItemActive : styles.navItem}
                key={item.id}
                type="button"
                onClick={() => {
                  setActiveNav(item.id);
                  setStatusMessage(`${item.label} 패널 선택`);
                }}
              >
                <Icon size={18} />
                {item.label}
              </button>
            );
          })}
        </nav>
        <div className={styles.brokerBox}>
          <span>{t.broker}</span>
          <strong>{t.demoAccount}</strong>
          <small>{t.connected}</small>
          <div>
            <span>{t.buyingPower}</span>
            <strong>{formatMoney(cash)}</strong>
          </div>
          <div>
            <span>{t.executionMode}</span>
            <strong>{t.paperOnly}</strong>
          </div>
        </div>
      </aside>

      <section className={styles.mainStage}>
        <header className={styles.topbar}>
          <div>
            <span className={styles.productName}>{t.autoTrading}</span>
            <h1>{t.appName}</h1>
          </div>
          <div className={styles.marketTicker} aria-label="Market overview">
            {marketFeed.map((feed) => (
              <div key={feed.label}>
                <span>{feed.label}</span>
                <strong>{feed.value}</strong>
                <small className={feed.positive ? styles.positive : styles.negative}>{feed.change}</small>
              </div>
            ))}
          </div>
          <div className={styles.headerActions}>
            <label className={styles.languageSelect}>
              <span>{t.language}</span>
              <select value={language} onChange={(event) => setLanguage(event.target.value as Language)}>
                <option value="en">English</option>
                <option value="ko">{"\uD55C\uAD6D\uC5B4"}</option>
              </select>
            </label>
            <button
              className={styles.iconButton}
              type="button"
              aria-label="Notifications"
              onClick={() => setStatusMessage("자동매매 알림: 현재 모의 계좌만 사용 중")}
            >
              <Bell size={18} />
            </button>
            <button
              className={styles.iconButton}
              type="button"
              aria-label="Settings"
              onClick={() => {
                setActiveNav("settings");
                setStatusMessage("설정: 1초 갱신 / 모의투자 / 2% 손절");
              }}
            >
              <Settings size={18} />
            </button>
          </div>
        </header>

        <section className={styles.controlBand} aria-labelledby="search-title">
          <div className={styles.marketTabs} aria-label="Market tabs">
            {(["domestic", "overseas"] as MarketScope[]).map((scope) => (
              <button
                className={scope === marketScope ? styles.marketTabActive : styles.marketTab}
                data-testid={`market-tab-${scope}`}
                key={scope}
                type="button"
                onClick={() => selectMarket(scope)}
              >
                {scope === "domestic" ? t.domestic : t.overseas}
              </button>
            ))}
          </div>
          <label className={styles.searchBox}>
            <Search size={18} aria-hidden="true" />
            <span className={styles.visuallyHidden} id="search-title">
              {t.searchTitle}
            </span>
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t.searchPlaceholder} />
            {query ? (
              <button type="button" onClick={() => setQuery("")} aria-label="Clear search">
                <X size={16} />
              </button>
            ) : null}
          </label>
          <div className={styles.marketStatus}>
            <span>{t.market}</span>
            <strong>
              <span aria-hidden="true" />
              {t.open}
            </strong>
            <small>{dataModeLabel}</small>
            <button
              className={styles.refreshButton}
              type="button"
              onClick={() => setRefreshKey((currentKey) => currentKey + 1)}
              aria-label={t.refreshQuotes}
            >
              <RefreshCw size={14} />
            </button>
          </div>
        </section>

        <section className={styles.workspace} aria-label="Stock workspace">
          <div className={styles.resultsPanel}>
            <div className={styles.panelHeader}>
              <div>
                <span>{t.results}</span>
                <strong>
                  {filteredStocks.length} {t.symbols}
                </strong>
              </div>
            </div>
            {dataStatus === "error" && dataError ? (
              <div className={styles.dataAlert}>
                <Activity size={16} />
                <span>{dataError}</span>
              </div>
            ) : null}
            <div className={styles.stockList}>
              {filteredStocks.length ? (
                filteredStocks.map((stock) => (
                  <button
                    className={`${styles.stockRow} ${stock.symbol === selectedStock.symbol ? styles.stockRowSelected : ""}`}
                    key={stock.symbol}
                    type="button"
                    onClick={() => {
                      setSelectedSymbol(stock.symbol);
                      setActivePoint(null);
                    }}
                  >
                    <span>
                      <strong>
                        {stock.symbol}
                        <em>#{stock.rank}</em>
                      </strong>
                      <small>{stockName(stock, language)}</small>
                    </span>
                    <span>
                      <b>{formatPrice(stock)}</b>
                      <small className={stock.change >= 0 ? styles.positive : styles.negative}>
                        {stock.change >= 0 ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                        {stock.change > 0 ? "+" : ""}
                        {stock.change.toFixed(2)}%
                      </small>
                    </span>
                  </button>
                ))
              ) : (
                <p className={styles.emptyState}>{t.noMatches}</p>
              )}
            </div>
          </div>

          <div className={styles.chartPanel}>
            <div className={styles.chartHeader}>
              <div>
                <span>
                  {selectedStock.market} / {t.deskMode}
                </span>
                <h2>
                  {selectedStock.symbol}
                  <small>{stockName(selectedStock, language)}</small>
                </h2>
              </div>
              <button
                className={watchlist.includes(selectedStock.symbol) ? styles.watchButtonActive : styles.watchButton}
                type="button"
                onClick={() => toggleWatchlist(selectedStock.symbol)}
              >
                <Star size={17} fill={watchlist.includes(selectedStock.symbol) ? "currentColor" : "none"} />
                {watchlist.includes(selectedStock.symbol) ? t.watchlist : "+ Watch"}
              </button>
            </div>

            <div className={styles.quoteStrip}>
              <div>
                <span>{t.lastPrice}</span>
                <strong>{formatPrice(selectedStock)}</strong>
              </div>
              <div>
                <span>{t.portfolioSignal}</span>
                <strong>{signalLabel(selectedStock.signal, language)}</strong>
              </div>
              <div>
                <span>{t.sector}</span>
                <strong>{sectorName(selectedStock, language)}</strong>
              </div>
              <div>
                <span>Market cap</span>
                <strong>{formatCompactNumber(selectedStock.marketCap)}B</strong>
              </div>
            </div>
            <div className={styles.sourceMeta}>
              <span>{selectedStock.source ?? "Sample + 1s simulation"}</span>
              <span>
                {t.updated} {formatFetchedAt(selectedStock.fetchedAt ?? latestFetchedAt, language)}
              </span>
              <span>Volume {formatCompactNumber(selectedStock.volume)}</span>
              <span>{statusMessage}</span>
            </div>

            <div className={styles.chartControls}>
              <div className={styles.chartTypeTabs} aria-label={t.chartType}>
                {(["candle", "line"] as ChartType[]).map((type) => (
                  <button
                    key={type}
                    className={type === chartType ? styles.rangeActive : ""}
                    data-testid={`chart-type-${type}`}
                    type="button"
                    onClick={() => setChartType(type)}
                  >
                    {type === "candle" ? <CandlestickChart size={15} /> : <LineChart size={15} />}
                    {type === "candle" ? t.candle : t.line}
                  </button>
                ))}
              </div>
              <div className={styles.rangeTabs} aria-label={t.chartRange}>
                {ranges.map((rangeKey) => (
                  <button
                    key={rangeKey}
                    className={rangeKey === range ? styles.rangeActive : ""}
                    data-testid={`range-${rangeKey}`}
                    type="button"
                    onClick={() => {
                      setRange(rangeKey);
                      setActivePoint(null);
                    }}
                  >
                    {t.rangeLabels[rangeKey]}
                  </button>
                ))}
              </div>
            </div>

            <div className={styles.chartCanvas}>
              <svg
                role="img"
                aria-label={`${selectedStock.symbol} ${range} price chart`}
                viewBox={`0 0 ${chartWidth} ${chartHeight}`}
                onPointerMove={handleChartPointerMove}
                onPointerLeave={() => setActivePoint(null)}
              >
                <defs>
                  <linearGradient id="priceArea" x1="0" x2="0" y1="0" y2="1">
                    <stop offset="0%" stopColor="#64748b" stopOpacity="0.24" />
                    <stop offset="100%" stopColor="#0f172a" stopOpacity="0" />
                  </linearGradient>
                </defs>
                {yAxisTicks.map((tickValue) => {
                  const y = yFor(tickValue, chartMin, chartMax, chartHeight, 20, 52);

                  return (
                    <g key={tickValue.toFixed(2)}>
                      <line className={styles.gridLine} x1={60} x2={chartWidth - 26} y1={y} y2={y} />
                      <text className={styles.axisLabel} x={8} y={y + 4}>
                        {selectedStock.currency === "KRW" ? Math.round(tickValue).toLocaleString("ko-KR") : tickValue.toFixed(2)}
                      </text>
                    </g>
                  );
                })}
                {xAxisIndexes.map((index) => {
                  const x = xFor(index, selectedPoints.length, chartWidth, 60, 26);

                  return (
                    <g key={`${range}-${index}`}>
                      <line className={styles.verticalGridLine} x1={x} x2={x} y1={20} y2={chartHeight - 52} />
                      <text className={styles.axisLabel} textAnchor="middle" x={x} y={chartHeight - 12}>
                        {formatChartPointLabel(selectedPoints[index], range, language)}
                      </text>
                    </g>
                  );
                })}
                <g className={styles.volumeLayer}>
                  {selectedPoints.map((point, index) => {
                    const x = xFor(index, selectedPoints.length, chartWidth, 60, 26);
                    const height = ((point.volume || 0) / volumeMax) * 36;

                    return (
                      <rect
                        className={point.close >= point.open ? styles.volumeUp : styles.volumeDown}
                        height={height}
                        key={`v-${index}`}
                        width={Math.max(2, candleWidth * 0.8)}
                        x={x - candleWidth * 0.4}
                        y={chartHeight - 52 - height}
                      />
                    );
                  })}
                </g>
                {chartType === "line" ? (
                  <>
                    <path
                      className={styles.areaPath}
                      d={`${path} L ${chartWidth - 26} ${chartHeight - 52} L 60 ${chartHeight - 52} Z`}
                    />
                    <path className={styles.pricePath} d={path} />
                  </>
                ) : (
                  <g className={styles.candleLayer}>
                    {selectedPoints.map((point, index) => {
                      const x = xFor(index, selectedPoints.length, chartWidth, 60, 26);
                      const openY = yFor(point.open, chartMin, chartMax, chartHeight, 20, 52);
                      const closeY = yFor(point.close, chartMin, chartMax, chartHeight, 20, 52);
                      const highY = yFor(point.high, chartMin, chartMax, chartHeight, 20, 52);
                      const lowY = yFor(point.low, chartMin, chartMax, chartHeight, 20, 52);
                      const isUp = point.close >= point.open;
                      const bodyTop = Math.min(openY, closeY);
                      const bodyHeight = Math.max(Math.abs(closeY - openY), 2);

                      return (
                        <g className={isUp ? styles.candleUp : styles.candleDown} key={`${range}-${index}`}>
                          <line x1={x} x2={x} y1={highY} y2={lowY} />
                          <rect x={x - candleWidth / 2} y={bodyTop} width={candleWidth} height={bodyHeight} />
                        </g>
                      );
                    })}
                  </g>
                )}
                <line className={styles.activeLine} x1={activeX} x2={activeX} y1={20} y2={chartHeight - 52} />
                <circle className={styles.activeDot} cx={activeX} cy={activeY} r="5" />
              </svg>
              <div className={styles.chartTooltip} style={{ left: `${(activeX / chartWidth) * 100}%` }}>
                <span>{formatChartPointLabel(selectedPoint, range, language)}</span>
                <strong>{selectedStock.currency === "KRW" ? formatMoney(selectedPoint.value) : formatMoney(selectedPoint.value, "USD")}</strong>
                <small>O {selectedPoint.open.toFixed(selectedStock.currency === "KRW" ? 0 : 2)} / C {selectedPoint.close.toFixed(selectedStock.currency === "KRW" ? 0 : 2)}</small>
              </div>
            </div>

            <div className={styles.chartFoot}>
              <div>
                <span>{t.rangeMove}</span>
                <strong className={rangeMove >= 0 ? styles.positive : styles.negative}>
                  {rangeMove >= 0 ? "+" : ""}
                  {rangeMove.toFixed(2)}%
                </strong>
              </div>
              <div>
                <span>{t.rangeHigh}</span>
                <strong>{selectedStock.currency === "KRW" ? formatMoney(Math.max(...candleExtremes)) : Math.max(...candleExtremes).toFixed(2)}</strong>
              </div>
              <div>
                <span>{t.rangeLow}</span>
                <strong>{selectedStock.currency === "KRW" ? formatMoney(Math.min(...candleExtremes)) : Math.min(...candleExtremes).toFixed(2)}</strong>
              </div>
              <div>
                <span>{t.signalQueue}</span>
                <strong>{signalLabel(selectedStock.signal, language)}</strong>
              </div>
            </div>
          </div>

          <aside className={styles.watchPanel} aria-labelledby="watch-title">
            <div className={styles.panelHeader}>
              <div>
                <span id="watch-title">{t.watchlist}</span>
                <strong>
                  {watchedStocks.length} {t.tracked}
                </strong>
              </div>
            </div>
            <div className={styles.watchList}>
              {watchedStocks.map((stock) => (
                <button className={styles.watchRow} key={stock.symbol} type="button" onClick={() => setSelectedSymbol(stock.symbol)}>
                  <span>
                    <strong>{stock.symbol}</strong>
                    <small>{signalLabel(stock.signal, language)}</small>
                  </span>
                  <span className={stock.change >= 0 ? styles.positive : styles.negative}>
                    {stock.change > 0 ? "+" : ""}
                    {stock.change.toFixed(2)}%
                  </span>
                </button>
              ))}
            </div>
            <div className={styles.simPanel}>
              <div className={styles.simHeader}>
                <Bot size={18} />
                <strong>{t.portfolioSignalPanel}</strong>
              </div>
              <div className={styles.accountGrid}>
                <div>
                  <span>{t.accountValue}</span>
                  <strong>{formatMoney(accountValue)}</strong>
                </div>
                <div>
                  <span>{t.pnl}</span>
                  <strong className={pnl >= 0 ? styles.positive : styles.negative}>
                    {pnl >= 0 ? "+" : ""}
                    {formatMoney(pnl)}
                  </strong>
                </div>
              </div>
              <div className={styles.simActions}>
                <label className={styles.autoToggle}>
                  <input
                    checked={autoRun}
                    data-testid="auto-run-toggle"
                    onChange={(event) => setAutoRun(event.currentTarget.checked)}
                    type="checkbox"
                  />
                  <span>{autoRun ? <Pause size={15} /> : <Play size={15} />}</span>
                  {autoRun ? t.stop : t.start}
                </label>
                <button data-testid="simulation-reset" type="button" onClick={resetSimulation}>
                  <RotateCcw size={15} />
                  {t.reset}
                </button>
              </div>
              <div className={styles.ruleList}>
                <span>{t.activeTheme}: {activeTheme ? themeName(activeTheme, language) : "-"}</span>
                <span>{t.stopLoss}</span>
                <span>거래비용 {(oneWayTradingCostRate * 100).toFixed(3)}% / 편도</span>
                <span>{t.exitRule}</span>
              </div>
              <div className={styles.positionList}>
                {positions.length ? (
                  positions.map((position) => {
                    const stock = stocks.find((item) => item.symbol === position.symbol);
                    const value = liquidationValue(position, stock);

                    return (
                      <div key={position.symbol}>
                        <strong>{position.symbol}</strong>
                        <span>{formatMoney(value)}</span>
                      </div>
                    );
                  })
                ) : (
                  <p>{autoRun ? "Waiting for next entry" : "Paused"}</p>
                )}
              </div>
            </div>
          </aside>
        </section>

        <section className={styles.lowerGrid}>
          <div className={styles.signalPanel}>
            <div className={styles.panelHeader}>
              <div>
                <span>{t.portfolioSignalPanel}</span>
                <strong>{activeTheme ? themeName(activeTheme, language) : "-"}</strong>
              </div>
            </div>
            <div className={styles.signalBody}>
              <div className={styles.scoreRing}>
                <span>{activeTheme ? themeMomentum(activeTheme).toFixed(1) : "0.0"}</span>
              </div>
              <div className={styles.signalTable}>
                <span>{t.topSignals}</span>
                {targetStocks.map((stock) => (
                  <div key={stock.symbol}>
                    <strong>{stock.symbol}</strong>
                    <span>{stockName(stock, language)}</span>
                    <small>{stock.change > 0 ? "+" : ""}{stock.change.toFixed(2)}%</small>
                  </div>
                ))}
              </div>
            </div>
          </div>
          <div className={styles.researchPanel}>
            <div className={styles.panelHeader}>
              <div>
                <span>{t.researchNotes}</span>
                <strong>{marketScope === "domestic" ? "KOSPI/KOSDAQ" : "US market"}</strong>
              </div>
            </div>
            <div className={styles.themeGrid}>
              {marketThemes.map((theme) => (
                <button
                  className={theme.id === activeTheme?.id ? styles.themeCardActive : styles.themeCard}
                  key={theme.id}
                  type="button"
                  onClick={() => focusTheme(theme)}
                >
                  <span>{themeName(theme, language)}</span>
                  <strong>{themeMomentum(theme).toFixed(2)}</strong>
                  <svg className={styles.themeSparkline} viewBox="0 0 142 34" aria-hidden="true">
                    <path d={themeSparklinePath(theme)} />
                  </svg>
                  <small>{theme.stocks.slice(0, 3).map((stock) => stock.symbol).join(" / ")}</small>
                </button>
              ))}
            </div>
            <div className={styles.tradeLog}>
              {tradeLog.map((entry, index) => (
                <span key={`${index}-${entry}`}>{entry}</span>
              ))}
            </div>
          </div>
        </section>
      </section>
    </main>
  );
}
