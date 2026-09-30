"use client";

import {
  Activity,
  Bell,
  Bot,
  Home,
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
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import styles from "./page.module.css";

type RangeKey = "LIVE" | "1D" | "1W" | "1M" | "1Y" | "5Y" | "ALL";
type MarketScope = "domestic" | "overseas";
type Language = "en" | "ko";
type Signal = "Buy" | "Watch" | "Hold";
type UniverseMode = "core" | "all";

type ChartPoint = {
  label: string;
  timestamp?: string;
  source?: string;
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
  strategyFetchedAt?: number;
  fxRate?: number;
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
  mode?: UniverseMode;
  refreshed_at?: string;
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

type TossPrice = { symbol: string; lastPrice: string; currency: "KRW" | "USD"; timestamp: string };
type TossCandle = { timestamp: string; openPrice: string; highPrice: string; lowPrice: string; closePrice: string; volume: string };
type ProfitPoint = { timestamp: number; value: number };

type DataStatus = "idle" | "loading" | "ready" | "error";

const defaultPaperCash = 100_000_000;
const usdKrw = 1380; // Sample-only fallback; connected quotes carry the actual FX rate.
const paperDomesticCommissionRate = 0.00015;
const paperUsCommissionRate = 0.001;
const usSecSellFeeRate = 0; // Commission estimate only; excludes taxes and other charges.
const themeHoldingLimit = 5;
const portfolioTargetSize = 3;
const positionStopLossRate = 0.02;
const sidecarDrawdownRate = 0.05;
const minThemeMomentumForEntry = 0.12;
const maRolloverSlopeBuffer = 0.0025;
const maRolloverSpreadBuffer = 0.004;
const maRolloverThemeMomentumFloor = -0.18;
const quotePollingMs = 30_000;
const themeRefreshCooldownMs = 60_000;
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
    liveDataMode: "Toss market data",
    loadingQuotes: "Loading quotes",
    quoteError: "Quote sync error",
    refreshQuotes: "Refresh quotes",
    themeModeCore: "Core",
    themeModeAll: "Extended",
    refreshThemes: "Refresh TOP5",
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
    researchNotes: "Theme TOP5",
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
    stopLoss: "2% stop / 5% sidecar",
    exitRule: "Held-stock MA break / theme rollover / 5 min to close",
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
    liveDataMode: "Toss market data",
    loadingQuotes: "\uC2DC\uC138 \uBD88\uB7EC\uC624\uB294 \uC911",
    quoteError: "\uC2DC\uC138 \uC5F0\uB3D9 \uC624\uB958",
    refreshQuotes: "\uC2DC\uC138 \uC0C8\uB85C\uACE0\uCE68",
    themeModeCore: "\uCF54\uC5B4",
    themeModeAll: "\uD655\uC7A5",
    refreshThemes: "\uD14C\uB9C8 TOP5 \uAC31\uC2E0",
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
    researchNotes: "\uD14C\uB9C8 TOP5",
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
    stopLoss: "2% \uC190\uC808 / 5% \uC0AC\uC774\uB4DC\uCE74",
    exitRule: "\uBCF4\uC720 MA \uAEBC\uC9D0/\uD14C\uB9C8 \uC774\uD0C8/\uC7A5\uB9C8\uAC10 5\uBD84",
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
    id: "domestic-defense",
    name: "Korea Defense",
    nameKo: "\uAD6D\uB0B4 \uBC29\uC0B0",
    region: "domestic" as const,
    stocks: [
      ["012450", "Hanwha Aerospace", "\uD55C\uD654\uC5D0\uC5B4\uB85C\uC2A4\uD398\uC774\uC2A4", "KOSPI", 1084000, 2.18, 54_000],
      ["042660", "Hanwha Ocean", "\uD55C\uD654\uC624\uC158", "KOSPI", 123400, 1.82, 37_800],
      ["064350", "Hyundai Rotem", "\uD604\uB300\uB85C\uD15C", "KOSPI", 213000, 1.64, 23_200],
      ["047810", "Korea Aerospace", "\uD55C\uAD6D\uD56D\uACF5\uC6B0\uC8FC", "KOSPI", 147600, 1.18, 14_300],
      ["079550", "LIG Nex1", "LIG\uB125\uC2A4\uC6D0", "KOSPI", 426000, 1.42, 9_400],
      ["272210", "Hanwha Systems", "\uD55C\uD654\uC2DC\uC2A4\uD15C", "KOSPI", 99500, 0.92, 18_000],
      ["103140", "Poongsan", "\uD48D\uC0B0", "KOSPI", 75500, 0.78, 2_100],
      ["077970", "STX Engine", "STX\uC5D4\uC9C4", "KOSPI", 36650, 0.58, 1_470],
      ["003570", "SNT Dynamics", "SNT\uB2E4\uC774\uB0B4\uBBF9\uC2A4", "KOSPI", 43600, 0.64, 1_440],
      ["064960", "SNT Motiv", "SNT\uBAA8\uD2F0\uBE0C", "KOSPI", 31150, 0.52, 830],
    ],
  },
] as const;

const additionalThemeSeed = [
  {
    id: "quantum-computing",
    name: "Quantum Computing",
    nameKo: "\uc591\uc790\ucef4\ud4e8\ud130",
    region: "overseas" as const,
    stocks: [
      ["IBM", "IBM", "IBM", "NYSE", 284.8, 1.24, 2_620_000],
      ["GOOGL", "Alphabet Class A", "Alphabet Class A", "NASDAQ", 182.34, 0.88, 2_245_000],
      ["MSFT", "Microsoft", "Microsoft", "NASDAQ", 472.11, 0.72, 3_510_000],
      ["IONQ", "IonQ", "IonQ", "NYSE", 43.2, 2.82, 128_000],
      ["RGTI", "Rigetti Computing", "Rigetti Computing", "NASDAQ", 12.18, 2.34, 74_000],
      ["QBTS", "D-Wave Quantum", "D-Wave Quantum", "NYSE", 15.42, 1.96, 68_000],
      ["QUBT", "Quantum Computing Inc.", "Quantum Computing Inc.", "NASDAQ", 9.62, 1.44, 42_000],
      ["HON", "Honeywell", "Honeywell", "NASDAQ", 228.6, 0.42, 148_000],
      ["ARQQ", "Arqit Quantum", "Arqit Quantum", "NASDAQ", 18.24, 1.08, 31_000],
      ["QTUM", "Defiance Quantum ETF", "Defiance Quantum ETF", "NYSEARCA", 82.46, 0.64, 24_000],
    ],
  },
  {
    id: "power-grid",
    name: "Power and Grid",
    nameKo: "\uc804\ub825/\uadf8\ub9ac\ub4dc",
    region: "overseas" as const,
    stocks: [
      ["GEV", "GE Vernova", "GE Vernova", "NYSE", 512.4, 1.72, 142_000],
      ["ETN", "Eaton", "Eaton", "NYSE", 358.2, 1.26, 138_000],
      ["PWR", "Quanta Services", "Quanta Services", "NYSE", 318.7, 1.54, 91_000],
      ["VRT", "Vertiv", "Vertiv", "NYSE", 124.6, 1.88, 63_000],
      ["HUBB", "Hubbell", "Hubbell", "NYSE", 412.8, 0.84, 29_000],
      ["ABBNY", "ABB ADR", "ABB ADR", "OTC", 58.4, 0.62, 119_000],
      ["SBGSY", "Schneider Electric ADR", "Schneider Electric ADR", "OTC", 55.6, 0.78, 112_000],
      ["AEP", "American Electric Power", "American Electric Power", "NASDAQ", 104.2, 0.36, 54_000],
      ["NEE", "NextEra Energy", "NextEra Energy", "NYSE", 78.1, 0.28, 162_000],
      ["SO", "Southern Company", "Southern Company", "NYSE", 91.7, 0.31, 99_000],
    ],
  },
  {
    id: "data-centers",
    name: "Data Centers",
    nameKo: "\ub370\uc774\ud130\uc13c\ud130",
    region: "overseas" as const,
    stocks: [
      ["EQIX", "Equinix", "Equinix", "NASDAQ", 816.2, 0.74, 78_000],
      ["DLR", "Digital Realty", "Digital Realty", "NYSE", 174.5, 0.88, 58_000],
      ["AMT", "American Tower", "American Tower", "NYSE", 194.8, 0.22, 91_000],
      ["VRT", "Vertiv", "Vertiv", "NYSE", 124.6, 1.92, 63_000],
      ["ETN", "Eaton", "Eaton", "NYSE", 358.2, 1.18, 138_000],
      ["ANET", "Arista Networks", "Arista Networks", "NYSE", 96.4, 1.12, 121_000],
      ["SMCI", "Super Micro Computer", "Super Micro Computer", "NASDAQ", 48.7, 1.64, 28_000],
      ["DELL", "Dell Technologies", "Dell Technologies", "NYSE", 126.3, 0.94, 88_000],
      ["NVDA", "NVIDIA Corp.", "NVIDIA Corp.", "NASDAQ", 214.75, 1.52, 5_280_000],
      ["AVGO", "Broadcom Inc.", "Broadcom Inc.", "NASDAQ", 1812.4, 1.06, 745_000],
    ],
  },
  {
    id: "nuclear-energy",
    name: "Nuclear Energy",
    nameKo: "\uc6d0\uc804/\uc6b0\ub77c\ub284",
    region: "overseas" as const,
    stocks: [
      ["CEG", "Constellation Energy", "Constellation Energy", "NASDAQ", 318.4, 1.46, 99_000],
      ["VST", "Vistra", "Vistra", "NYSE", 184.2, 1.68, 65_000],
      ["CCJ", "Cameco", "Cameco", "NYSE", 74.6, 1.08, 32_000],
      ["BWXT", "BWX Technologies", "BWX Technologies", "NYSE", 138.1, 0.84, 13_000],
      ["SMR", "NuScale Power", "NuScale Power", "NYSE", 38.2, 2.08, 11_000],
      ["OKLO", "Oklo", "Oklo", "NYSE", 52.3, 2.42, 9_600],
      ["LEU", "Centrus Energy", "Centrus Energy", "NYSE", 112.8, 1.26, 1_900],
      ["UEC", "Uranium Energy", "Uranium Energy", "NYSEAMERICAN", 9.8, 0.96, 4_200],
      ["URA", "Global X Uranium ETF", "Global X Uranium ETF", "NYSEARCA", 43.6, 0.72, 3_900],
      ["NLR", "VanEck Uranium and Nuclear ETF", "VanEck Uranium and Nuclear ETF", "NYSEARCA", 102.4, 0.58, 1_200],
    ],
  },
  {
    id: "robotics-humanoids",
    name: "Robotics and Humanoids",
    nameKo: "\ub85c\ubd07/\ud734\uba38\ub178\uc774\ub4dc",
    region: "overseas" as const,
    stocks: [
      ["ISRG", "Intuitive Surgical", "Intuitive Surgical", "NASDAQ", 548.7, 0.96, 191_000],
      ["TSLA", "Tesla", "Tesla", "NASDAQ", 198.3, 1.18, 633_000],
      ["TER", "Teradyne", "Teradyne", "NASDAQ", 141.2, 0.74, 22_000],
      ["SYM", "Symbotic", "Symbotic", "NASDAQ", 42.8, 1.86, 24_000],
      ["PATH", "UiPath", "UiPath", "NYSE", 14.7, 0.82, 8_200],
      ["ABBNY", "ABB ADR", "ABB ADR", "OTC", 58.4, 0.54, 119_000],
      ["FANUY", "Fanuc ADR", "Fanuc ADR", "OTC", 14.9, 0.36, 32_000],
      ["ROBO", "ROBO Global Robotics ETF", "ROBO Global Robotics ETF", "NYSEARCA", 59.8, 0.48, 1_500],
      ["BOTZ", "Global X Robotics ETF", "Global X Robotics ETF", "NASDAQ", 33.2, 0.52, 2_800],
      ["IRBT", "iRobot", "iRobot", "NASDAQ", 8.1, 0.22, 240],
    ],
  },
  {
    id: "defense",
    name: "Defense",
    nameKo: "\ubc29\uc0b0",
    region: "overseas" as const,
    stocks: [
      ["RTX", "RTX", "RTX", "NYSE", 146.8, 0.72, 196_000],
      ["LMT", "Lockheed Martin", "Lockheed Martin", "NYSE", 488.6, 0.58, 116_000],
      ["NOC", "Northrop Grumman", "Northrop Grumman", "NYSE", 518.4, 0.66, 76_000],
      ["GD", "General Dynamics", "General Dynamics", "NYSE", 294.6, 0.44, 81_000],
      ["LHX", "L3Harris Technologies", "L3Harris Technologies", "NYSE", 238.1, 0.54, 45_000],
      ["HII", "Huntington Ingalls", "Huntington Ingalls", "NYSE", 244.9, 0.31, 9_700],
      ["LDOS", "Leidos", "Leidos", "NYSE", 152.4, 0.47, 20_000],
      ["TXT", "Textron", "Textron", "NYSE", 87.8, 0.36, 16_000],
      ["KTOS", "Kratos Defense", "Kratos Defense", "NASDAQ", 34.7, 1.02, 5_200],
      ["ITA", "iShares US Aerospace & Defense ETF", "iShares US Aerospace & Defense ETF", "BATS", 151.6, 0.48, 6_100],
    ],
  },
  {
    id: "aerospace-space",
    name: "Aerospace and Space",
    nameKo: "\uc6b0\uc8fc\ud56d\uacf5",
    region: "overseas" as const,
    stocks: [
      ["BA", "Boeing", "Boeing", "NYSE", 183.5, 0.84, 113_000],
      ["AIR", "Airbus ADR", "Airbus ADR", "OTC", 43.2, 0.62, 138_000],
      ["GE", "GE Aerospace", "GE Aerospace", "NYSE", 251.2, 0.76, 272_000],
      ["RTX", "RTX", "RTX", "NYSE", 146.8, 0.62, 196_000],
      ["LMT", "Lockheed Martin", "Lockheed Martin", "NYSE", 488.6, 0.42, 116_000],
      ["NOC", "Northrop Grumman", "Northrop Grumman", "NYSE", 518.4, 0.48, 76_000],
      ["RKLB", "Rocket Lab", "Rocket Lab", "NASDAQ", 28.4, 1.74, 14_000],
      ["ASTS", "AST SpaceMobile", "AST SpaceMobile", "NASDAQ", 46.8, 2.12, 12_000],
      ["IRDM", "Iridium Communications", "Iridium Communications", "NASDAQ", 28.7, 0.38, 3_300],
      ["UFO", "Procure Space ETF", "Procure Space ETF", "NASDAQ", 22.8, 0.42, 120],
    ],
  },
  {
    id: "biotech",
    name: "Biotech",
    nameKo: "\ubc14\uc774\uc624",
    region: "overseas" as const,
    stocks: [
      ["AMGN", "Amgen", "Amgen", "NASDAQ", 306.8, 0.32, 164_000],
      ["GILD", "Gilead Sciences", "Gilead Sciences", "NASDAQ", 111.2, 0.44, 139_000],
      ["REGN", "Regeneron", "Regeneron", "NASDAQ", 742.5, 0.58, 81_000],
      ["VRTX", "Vertex Pharmaceuticals", "Vertex Pharmaceuticals", "NASDAQ", 474.7, 0.64, 122_000],
      ["MRNA", "Moderna", "Moderna", "NASDAQ", 38.6, 1.14, 15_000],
      ["BIIB", "Biogen", "Biogen", "NASDAQ", 155.2, 0.46, 22_000],
      ["ILMN", "Illumina", "Illumina", "NASDAQ", 118.9, 0.72, 19_000],
      ["BNTX", "BioNTech", "BioNTech", "NASDAQ", 104.8, 0.52, 25_000],
      ["ALNY", "Alnylam", "Alnylam", "NASDAQ", 284.4, 0.76, 37_000],
      ["CRSP", "CRISPR Therapeutics", "CRISPR Therapeutics", "NASDAQ", 58.2, 1.26, 5_500],
    ],
  },
  {
    id: "blockchain",
    name: "Blockchain",
    nameKo: "\ube14\ub85d\uccb4\uc778",
    region: "overseas" as const,
    stocks: [
      ["COIN", "Coinbase", "Coinbase", "NASDAQ", 312.4, 1.62, 78_000],
      ["MSTR", "MicroStrategy", "MicroStrategy", "NASDAQ", 1642.8, 2.08, 42_000],
      ["MARA", "MARA Holdings", "MARA Holdings", "NASDAQ", 22.4, 1.86, 7_800],
      ["RIOT", "Riot Platforms", "Riot Platforms", "NASDAQ", 13.2, 1.58, 4_100],
      ["CLSK", "CleanSpark", "CleanSpark", "NASDAQ", 18.9, 1.72, 5_400],
      ["HUT", "Hut 8", "Hut 8", "NASDAQ", 21.4, 1.36, 2_300],
      ["BITF", "Bitfarms", "Bitfarms", "NASDAQ", 2.6, 1.08, 1_100],
      ["GLXY", "Galaxy Digital", "Galaxy Digital", "NASDAQ", 24.8, 1.24, 8_600],
      ["BLOK", "Amplify Transformational Data ETF", "Amplify Transformational Data ETF", "NYSEARCA", 43.2, 0.88, 820],
      ["IBIT", "iShares Bitcoin Trust ETF", "iShares Bitcoin Trust ETF", "NASDAQ", 62.4, 0.94, 72_000],
    ],
  },
  {
    id: "us-inverse-etfs",
    name: "US Inverse ETFs",
    nameKo: "\ubbf8\uad6d \uc778\ubc84\uc2a4 ETF",
    region: "overseas" as const,
    stocks: [
      ["SH", "ProShares Short S&P500", "ProShares Short S&P500", "NYSEARCA", 38.2, -0.42, 1_600],
      ["PSQ", "ProShares Short QQQ", "ProShares Short QQQ", "NYSEARCA", 34.6, -0.58, 1_300],
      ["DOG", "ProShares Short Dow30", "ProShares Short Dow30", "NYSEARCA", 29.4, -0.22, 380],
      ["SDS", "ProShares UltraShort S&P500", "ProShares UltraShort S&P500", "NYSEARCA", 18.7, -0.86, 620],
      ["QID", "ProShares UltraShort QQQ", "ProShares UltraShort QQQ", "NYSEARCA", 24.3, -1.12, 520],
      ["SQQQ", "ProShares UltraPro Short QQQ", "ProShares UltraPro Short QQQ", "NASDAQ", 16.8, -1.72, 3_800],
      ["SPXU", "ProShares UltraPro Short S&P500", "ProShares UltraPro Short S&P500", "NYSEARCA", 22.6, -1.44, 980],
      ["TZA", "Direxion Daily Small Cap Bear 3X", "Direxion Daily Small Cap Bear 3X", "NYSEARCA", 14.4, -1.28, 430],
      ["SOXS", "Direxion Daily Semiconductor Bear 3X", "Direxion Daily Semiconductor Bear 3X", "NYSEARCA", 10.8, -2.08, 520],
      ["LABD", "Direxion Daily S&P Biotech Bear 3X", "Direxion Daily S&P Biotech Bear 3X", "NYSEARCA", 8.7, -1.36, 160],
    ],
  },
  {
    id: "korea-inverse-etfs",
    name: "Korea Inverse ETFs",
    nameKo: "\uad6d\ub0b4 \uc778\ubc84\uc2a4 ETF",
    region: "domestic" as const,
    stocks: [
      ["114800", "KODEX Inverse", "KODEX Inverse", "KOSPI", 983, -0.34, 2_300],
      ["252670", "KODEX 200 Futures Inverse 2X", "KODEX 200 Futures Inverse 2X", "KOSPI", 84, -0.72, 927],
      ["251340", "KODEX KOSDAQ150 Futures Inverse", "KODEX KOSDAQ150 Futures Inverse", "KOSPI", 3940, -0.42, 690],
      ["123310", "TIGER Inverse", "TIGER Inverse", "KOSPI", 5080, -0.31, 540],
      ["252710", "TIGER 200 Futures Inverse 2X", "TIGER 200 Futures Inverse 2X", "KOSPI", 86, -0.69, 430],
      ["250780", "TIGER KOSDAQ150 Futures Inverse", "TIGER KOSDAQ150 Futures Inverse", "KOSPI", 4820, -0.38, 390],
      ["253160", "ARIRANG 200 Futures Inverse 2X", "ARIRANG 200 Futures Inverse 2X", "KOSPI", 91, -0.66, 220],
      ["253230", "KOSEF 200 Futures Inverse 2X", "KOSEF 200 Futures Inverse 2X", "KOSPI", 88, -0.68, 190],
      ["252420", "KBSTAR 200 Futures Inverse 2X", "KBSTAR 200 Futures Inverse 2X", "KOSPI", 89, -0.65, 170],
      ["291610", "KOSEF KOSDAQ150 Futures Inverse", "KOSEF KOSDAQ150 Futures Inverse", "KOSPI", 5620, -0.36, 120],
    ],
  },
] as const;

const seededThemeUniverse = [...themeSeed, ...additionalThemeSeed] as const;
const coreThemeIds = new Set([
  "k-semi",
  "domestic-defense",
  "ai-semi",
  "us-platform",
  "us-inverse-etfs",
  "korea-inverse-etfs",
]);

function buildSeries(...unused: number[]): Record<RangeKey, ChartPoint[]> {
  void unused;
  return { LIVE: [], "1D": [], "1W": [], "1M": [], "1Y": [], "5Y": [], ALL: [] };
}

function buildUniverse(mode: UniverseMode = "core"): ThemeUniverse[] {
  return seededThemeUniverse.filter((theme) => mode === "all" || coreThemeIds.has(theme.id)).map((theme) => ({
    ...theme,
    stocks: theme.stocks.slice(0, themeHoldingLimit).map((row, index) => {
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
        strategy: index < portfolioTargetSize ? "Theme rotation TOP3" : "Theme watchlist TOP5",
        series: buildSeries(numericPrice, numericChange, index + theme.id.length),
      };
    }),
  }));
}

function stockFallbackPrice(symbol: string, region: MarketScope, rank: number) {
  const fallbackStock = buildUniverse("all")
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

function universeFromApi(payload: ThemeUniverseApiResponse, mode: UniverseMode): ThemeUniverse[] {
  if (!payload.themes.length) {
    return buildUniverse(mode);
  }

  return payload.themes.map((theme) => ({
    id: theme.key,
    name: theme.name,
    nameKo: theme.name_ko ?? theme.name,
    description: theme.description,
    region: theme.top_market_cap[0]?.region ?? "overseas",
    source: payload.source,
    stocks: theme.top_market_cap.slice(0, themeHoldingLimit).map((holding) => {
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
        strategy: holding.market_cap_rank <= portfolioTargetSize ? "API theme rotation TOP3" : "API theme TOP5",
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

function stockName(stock: Stock, language: Language) {
  return language === "ko" ? stock.localName : stock.name;
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
  return stock.currency === "KRW" ? stock.price : stock.price * (stock.fxRate ?? usdKrw);
}

function buyCostRate(stock: Stock) {
  return stock.region === "domestic" ? paperDomesticCommissionRate : paperUsCommissionRate;
}

function sellCostRate(stock: Stock) {
  return stock.region === "domestic" ? paperDomesticCommissionRate : paperUsCommissionRate + usSecSellFeeRate;
}

function tradingCostLabel(scope: MarketScope) {
  if (scope === "domestic") {
    return `KR ${formatRate(paperDomesticCommissionRate)} / side`;
  }

  return `US buy ${formatRate(paperUsCommissionRate)} · sell ${formatRate(paperUsCommissionRate + usSecSellFeeRate)}`;
}

function formatRate(rate: number) {
  return `${(rate * 100).toFixed(rate < 0.001 ? 5 : 3)}%`;
}

function liquidationValue(position: Position, stock: Stock | undefined) {
  if (!stock) {
    return 0;
  }

  return position.shares * priceToKrw(stock) * (1 - sellCostRate(stock));
}

function buildBalancedPaperPositions(targetStocks: Stock[], availableCash: number): Position[] {
  const targetAllocation = availableCash / Math.max(targetStocks.length, 1);
  const drafts = targetStocks.map((stock) => {
    const entryPrice = priceToKrw(stock);
    const entryCostRate = buyCostRate(stock);
    const unitCost = entryPrice * (1 + entryCostRate);
    const shares = Math.floor(targetAllocation / unitCost);
    const entryGrossValue = shares * entryPrice;
    const entryFee = entryGrossValue * entryCostRate;

    return {
      symbol: stock.symbol,
      shares,
      entryPrice,
      entryFee,
      entryValue: entryGrossValue + entryFee,
      unitCost,
      unitFee: entryPrice * entryCostRate,
    };
  });
  let remainingCash = availableCash - drafts.reduce((sum, draft) => sum + draft.entryValue, 0);

  while (drafts.some((draft) => draft.unitCost <= remainingCash)) {
    const nextDraft = drafts
      .filter((draft) => draft.unitCost <= remainingCash)
      .sort((left, right) => left.entryValue - right.entryValue || left.unitCost - right.unitCost)[0];

    nextDraft.shares += 1;
    nextDraft.entryValue += nextDraft.unitCost;
    nextDraft.entryFee += nextDraft.unitFee;
    remainingCash -= nextDraft.unitCost;
  }

  return drafts
    .filter((draft) => draft.shares > 0)
    .map((draft) => ({
      symbol: draft.symbol,
      shares: draft.shares,
      entryPrice: draft.entryPrice,
      entryValue: draft.entryValue,
      entryFee: draft.entryFee,
    }));
}

function movingAverage(points: ChartPoint[], windowSize: number) {
  const slice = points.slice(-windowSize);
  return slice.reduce((sum, point) => sum + point.close, 0) / Math.max(slice.length, 1);
}

function trendFromPoints(points: ChartPoint[], fastWindow: number, slowWindow: number, comparisonOffset: number) {
  const fast = movingAverage(points, fastWindow);
  const previousFast = movingAverage(points.slice(0, -comparisonOffset), fastWindow);
  const slow = movingAverage(points, slowWindow);
  const safeSlow = slow || 1;
  const safePreviousFast = previousFast || fast || 1;
  const fastSpread = ((fast - slow) / safeSlow) * 100;
  const slope = ((fast - previousFast) / safePreviousFast) * 100;

  return {
    fast,
    previousFast,
    slow,
    rising: fast > previousFast && fast > slow,
    score: fastSpread + slope * 2,
  };
}

function stockMovingAverageTrend(stock: Stock) {
  return trendFromPoints(stock.series.LIVE, 8, 26, 4);
}

function stockLongTrendScore(stock: Stock) {
  const monthTrend = trendFromPoints(stock.series["1M"], 20, 60, 8);
  const yearTrend = trendFromPoints(stock.series["1Y"], 20, 80, 10);

  return monthTrend.score * 0.45 + yearTrend.score * 0.55;
}

function quoteFresh(stock: Stock) {
  return Boolean(stock.source && stock.fetchedAt && Date.now() - Date.parse(stock.fetchedAt) < 90_000);
}

function strategyReady(stock: Stock) {
  return quoteFresh(stock) && Boolean(stock.strategyFetchedAt && Date.now() - stock.strategyFetchedAt < 1_200_000) && stock.series.LIVE.length >= 26 && stock.series["1Y"].length >= 80;
}

function momentumScore(stock: Stock) {
  if (!strategyReady(stock)) return 0;
  const shortTrend = stockMovingAverageTrend(stock);
  const shortScore = shortTrend.rising ? shortTrend.score : shortTrend.score * 0.35;
  const longScore = stockLongTrendScore(stock);

  return shortScore + longScore * 0.65 + stock.change * 0.15;
}

function themeMomentum(theme: ThemeUniverse) {
  const leaders = theme.stocks.slice(0, themeHoldingLimit);

  return leaders.reduce((sum, stock) => sum + momentumScore(stock), 0) / Math.max(leaders.length, 1);
}

function isStockMovingAverageBroken(stock: Stock) {
  const trend = stockMovingAverageTrend(stock);
  const fastBelowSlow = trend.fast < trend.slow * (1 - maRolloverSpreadBuffer * 0.5);
  const fastTurnedDown = trend.fast < trend.previousFast * (1 - maRolloverSlopeBuffer * 0.5);

  return fastBelowSlow || (fastTurnedDown && trend.score < 0);
}

function isThemeUptrend(theme: ThemeUniverse) {
  const leaders = theme.stocks.slice(0, portfolioTargetSize);
  if (!leaders.every(strategyReady)) return false;
  const risingLeaders = leaders.filter((stock) => {
    const shortTrend = stockMovingAverageTrend(stock);

    return shortTrend.rising && stockLongTrendScore(stock) > 0;
  }).length;

  return themeMomentum(theme) > minThemeMomentumForEntry && risingLeaders >= Math.ceil(leaders.length * 0.6);
}

function isMovingAverageRollingOver(theme: ThemeUniverse) {
  const momentum = themeMomentum(theme);
  const rolloverSignals = theme.stocks.slice(0, themeHoldingLimit).map((stock) => {
    const trend = stockMovingAverageTrend(stock);

    const fastBelowSlow = trend.fast < trend.slow * (1 - maRolloverSpreadBuffer);
    const fastClearlyFalling = trend.fast < trend.previousFast * (1 - maRolloverSlopeBuffer);
    const scoreClearlyWeak = trend.score < maRolloverThemeMomentumFloor;

    return fastBelowSlow && fastClearlyFalling && scoreClearlyWeak;
  });

  return momentum < 0 && rolloverSignals.filter(Boolean).length >= Math.ceil(rolloverSignals.length * 0.7);
}

export default function StockDashboard() {
  const [query, setQuery] = useState("");
  const [marketScope, setMarketScope] = useState<MarketScope>("domestic");
  const [language, setLanguage] = useState<Language>("en");
  const [selectedSymbol, setSelectedSymbol] = useState("005930");
  const [watchlist, setWatchlist] = useState(["005930", "000660", "373220", "NVDA", "MSFT"]);
  const [universeMode, setUniverseMode] = useState<UniverseMode>("core");
  const [universes, setUniverses] = useState<ThemeUniverse[]>(() => buildUniverse("core"));
  const [dataStatus, setDataStatus] = useState<DataStatus>("idle");
  const [dataError, setDataError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const [universeRefreshKey, setUniverseRefreshKey] = useState(0);
  const [themeRefreshStatus, setThemeRefreshStatus] = useState<DataStatus>("idle");
  const [themeRefreshMessage, setThemeRefreshMessage] = useState("Core TOP5 universe ready");
  const [lastThemeRefreshAt, setLastThemeRefreshAt] = useState("");
  const [themeRefreshBlockedUntil, setThemeRefreshBlockedUntil] = useState(0);
  const [autoRun, setAutoRun] = useState(false);
  const [profitPoints, setProfitPoints] = useState<ProfitPoint[]>([]);
  const [brokerStatus, setBrokerStatus] = useState("Checking credentials");
  const [brokerConfigured, setBrokerConfigured] = useState(false);
  const [connectionBusy, setConnectionBusy] = useState(false);
  const latestPortfolio = useRef({ value: defaultPaperCash, fresh: false, syncedAt: 0 });
  const [lastQuoteSync, setLastQuoteSync] = useState(0);
  const sessionBaseline = useRef(defaultPaperCash);
  const symbolList = [...new Set(universes.flatMap(theme => theme.stocks.map(stock => stock.symbol)))].join(",");
  const [paperInitialCash, setPaperInitialCash] = useState(defaultPaperCash);
  const [paperCashInput, setPaperCashInput] = useState(String(defaultPaperCash));
  const [cash, setCash] = useState(defaultPaperCash);
  const [positions, setPositions] = useState<Position[]>([]);
  const [tradeLog, setTradeLog] = useState<string[]>([`Ready: ${defaultPaperCash.toLocaleString("en-US")} KRW paper account`]);
  const [sidecarAlert, setSidecarAlert] = useState("");
  const [tick, setTick] = useState(0);
  const [activeNav, setActiveNav] = useState("home");
  const [statusMessage, setStatusMessage] = useState("Waiting for Toss market data and strategy history");
  const [apiBlocked, setApiBlocked] = useState(false);

  const t = copy[language];
  const stocks = useMemo(() => universes.flatMap((theme) => theme.stocks), [universes]);
  const marketThemes = useMemo(() => universes.filter((theme) => theme.region === marketScope), [marketScope, universes]);
  const activeTheme = useMemo(
    () => [...marketThemes].sort((a, b) => themeMomentum(b) - themeMomentum(a))[0],
    [marketThemes],
  );
  const targetStocks = useMemo(() => activeTheme?.stocks.slice(0, portfolioTargetSize) ?? [], [activeTheme]);
  const marketStocks = useMemo(
    () => marketThemes.flatMap((theme) => theme.stocks).sort((a, b) => b.marketCap - a.marketCap),
    [marketThemes],
  );
  const strategySymbolList = [...new Set(marketStocks.map(stock => stock.symbol))].join(",");
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
  const filteredThemeGroups = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();

    return marketThemes
      .map((theme) => {
        const themeMatches =
          !normalizedQuery ||
          [theme.name, theme.nameKo, theme.description ?? ""].some((value) =>
            value.toLowerCase().includes(normalizedQuery),
          );
        const themeStocks = themeMatches
          ? theme.stocks
          : theme.stocks.filter((stock) =>
              [stock.symbol, stock.name, stock.localName, stock.market, stock.sector, stock.sectorKo].some((value) =>
                value.toLowerCase().includes(normalizedQuery),
              ),
            );

        return {
          theme,
          stocks: themeStocks,
        };
      })
      .filter((group) => group.stocks.length);
  }, [marketThemes, query]);
  const selectedStock =
    stocks.find((stock) => stock.symbol === selectedSymbol && stock.region === marketScope) ??
    marketStocks[0] ??
    stocks[0];

  const clearApiBlock = () => {
    if (!apiBlocked) {
      return;
    }

    setApiBlocked(false);
    setDataError("");
    setDataStatus("loading");
  };

  useEffect(() => {
    if (apiBlocked) {
      return;
    }

    const controller = new AbortController();

    async function loadThemeUniverse() {
      setThemeRefreshStatus("loading");
      try {
        const response = await fetch(`${apiBaseUrl}/universe/themes?mode=${universeMode}`, { signal: controller.signal });

        if (!response.ok) {
          const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
          throw new Error(payload?.detail ?? `Theme API request failed: ${response.status}`);
        }

        const payload = (await response.json()) as ThemeUniverseApiResponse;
        const nextUniverses = universeFromApi(payload, universeMode);

        if (!nextUniverses.length) {
          setThemeRefreshStatus("error");
          setThemeRefreshMessage("Theme API returned no symbols");
          setStatusMessage("테마 API 응답 없음");
          return;
        }

        setUniverses(current => {
          const previous = new Map(current.flatMap(theme => theme.stocks).map(stock => [stock.symbol, stock]));
          return nextUniverses.map(theme => ({ ...theme, stocks: theme.stocks.map(stock => {
            const known = previous.get(stock.symbol);
            return known ? { ...stock, price: known.price, change: known.change, source: known.source, fetchedAt: known.fetchedAt, fxRate: known.fxRate, strategyFetchedAt: known.strategyFetchedAt, series: known.series } : stock;
          }) }));
        });
        setThemeRefreshStatus("ready");
        setLastThemeRefreshAt(
          payload.refreshed_at
            ? new Date(payload.refreshed_at).toLocaleTimeString("ko-KR")
            : new Date().toLocaleTimeString("ko-KR"),
        );
        setThemeRefreshMessage(
          `${payload.mode === "all" || universeMode === "all" ? "Extended" : "Core"} TOP5 refreshed · ${nextUniverses.length} themes`,
        );
        setStatusMessage("Theme TOP5 refreshed");
      } catch (error) {
        if (!controller.signal.aborted) {
          const message = error instanceof Error ? error.message : "Theme API request failed.";
          setThemeRefreshStatus("error");
          setThemeRefreshMessage(`Theme API error: ${message}`);
          setStatusMessage(`테마 API 에러: ${message}`);
        }

        return;
      }
    }

    loadThemeUniverse();

    return () => controller.abort();
  }, [apiBlocked, universeMode, universeRefreshKey]);

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${apiBaseUrl}/brokers/toss/status`, { signal: controller.signal })
      .then(response => { if (!response.ok) throw new Error("Broker status unavailable"); return response.json(); })
      .then(payload => {
        setBrokerConfigured(payload.configured);
        setBrokerStatus(payload.configured ? "Credentials configured — verify connection" : "Setup required: TOSS_CLIENT_ID / TOSS_CLIENT_SECRET");
      }).catch(error => { if (!controller.signal.aborted) setBrokerStatus(error.message); });
    return () => controller.abort();
  }, [refreshKey]);

  useEffect(() => {
    if (!brokerConfigured) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function loadPrices() {
      try {
        const response = await fetch(`${apiBaseUrl}/brokers/toss/prices?symbols=${encodeURIComponent(symbolList)}`, { signal: controller.signal });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.detail ?? "Toss price request failed");
        if (!payload.data.length || !Number.isFinite(Number(payload.usd_krw)) || Number(payload.usd_krw) <= 0) throw new Error("Toss returned incomplete market data");
        setLastQuoteSync(Date.parse(payload.synced_at));
        const prices = new Map<string, TossPrice>(payload.data.map((p: TossPrice) => [p.symbol, p]));
        setUniverses(current => current.map(theme => ({ ...theme, stocks: theme.stocks.map(stock => {
          const price = prices.get(stock.symbol);
          if (!price || !Number.isFinite(Number(price.lastPrice)) || Number(price.lastPrice) <= 0) return stock;
          const previousClose = stock.series["1Y"].at(-2)?.close;
          return { ...stock, price: Number(price.lastPrice), currency: price.currency, change: previousClose ? (Number(price.lastPrice) / previousClose - 1) * 100 : 0, signal: stockSignal(previousClose ? (Number(price.lastPrice) / previousClose - 1) * 100 : 0),
            fetchedAt: payload.synced_at, fxRate: Number(payload.usd_krw), source: payload.source };
        }) })));
        setDataStatus("ready"); setDataError(""); setApiBlocked(false);
        setTick(current => current + 30);
      } catch (error) {
        if (!controller.signal.aborted) {
          setDataStatus("error"); setDataError(error instanceof Error ? error.message : "Toss price request failed");
        }
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(loadPrices, quotePollingMs);
      }
    }
    void loadPrices();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [brokerConfigured, symbolList, refreshKey]);

  useEffect(() => {
    if (!brokerConfigured || !autoRun) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function loadStrategy() {
      try {
        for (const symbol of strategySymbolList.split(",")) {
          const response = await fetch(`${apiBaseUrl}/brokers/toss/strategy/${encodeURIComponent(symbol)}`, { signal: controller.signal });
          const payload = await response.json();
          if (!response.ok) throw new Error(payload.detail ?? "Strategy data unavailable");
          const points = (candles: TossCandle[]): ChartPoint[] => candles.map(c => ({
            label: c.timestamp, timestamp: c.timestamp, value: Number(c.closePrice),
            open: Number(c.openPrice), high: Number(c.highPrice), low: Number(c.lowPrice),
            close: Number(c.closePrice), volume: Number(c.volume), source: "Toss Securities Open API",
          }));
          setUniverses(current => current.map(theme => ({ ...theme, stocks: theme.stocks.map(stock => stock.symbol !== symbol ? stock : {
            ...stock, strategyFetchedAt: Date.parse(payload.synced_at), series: { ...stock.series, LIVE: points(payload.minute), "1M": points(payload.daily), "1Y": points(payload.daily) },
          }) })));
        }
      } catch (error) {
        if (!controller.signal.aborted) setStatusMessage(error instanceof Error ? error.message : "Strategy data unavailable");
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(loadStrategy, 900_000);
      }
    }
    void loadStrategy();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [brokerConfigured, strategySymbolList, autoRun, refreshKey]);

  useEffect(() => {
    if (!autoRun) return;
    const timer = window.setInterval(() => {
      if (!latestPortfolio.current.fresh || Date.now() - latestPortfolio.current.syncedAt >= 90_000) return;
      setProfitPoints(current => [...current, { timestamp: Date.now(), value: latestPortfolio.current.value - sessionBaseline.current }]);
    }, 5_000);
    return () => window.clearInterval(timer);
  }, [autoRun]);

  useEffect(() => {
    if (!autoRun || dataStatus !== "ready" || !activeTheme || !targetStocks.length || !marketStocks.every(strategyReady) || !positions.every(p => stocks.some(s => s.symbol === p.symbol && strategyReady(s)))) {
      return;
    }

    const timeoutId = window.setTimeout(() => {
      const portfolioValue = positions.reduce((sum, position) => {
        const stock = stocks.find((item) => item.symbol === position.symbol);
        return sum + liquidationValue(position, stock);
      }, cash);
      const positionsEntryValue = positions.reduce((sum, position) => sum + position.entryValue, 0);
      const positionsLiquidationValue = Math.max(0, portfolioValue - cash);
      const lossTriggered = positions.some((position) => {
        const stock = stocks.find((item) => item.symbol === position.symbol);
        return stock ? liquidationValue(position, stock) <= position.entryValue * (1 - positionStopLossRate) : false;
      });
      const sidecarTriggered =
        positions.length > 0 &&
        positionsEntryValue > 0 &&
        positionsLiquidationValue <= positionsEntryValue * (1 - sidecarDrawdownRate);
      const now = new Date();
      const clock = new Intl.DateTimeFormat("en-GB", { timeZone: marketScope === "domestic" ? "Asia/Seoul" : "America/New_York", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(now);
      const [hour, minute] = clock.split(":").map(Number);
      const minutes = hour * 60 + minute;
      const closeMinutes = marketScope === "domestic" ? 930 : 960;
      const openMinutes = marketScope === "domestic" ? 540 : 570;
      const day = new Intl.DateTimeFormat("en-US", { timeZone: marketScope === "domestic" ? "Asia/Seoul" : "America/New_York", weekday: "short" }).format(now);
      const isCloseWindow = minutes >= closeMinutes - 5;
      const isMarketSession = day !== "Sat" && day !== "Sun" && minutes >= openMinutes && minutes < closeMinutes;
      const maRollingOver = isMovingAverageRollingOver(activeTheme);
      const heldStockMaBroken = positions.some((position) => {
        const stock = stocks.find((item) => item.symbol === position.symbol);

        return stock ? isStockMovingAverageBroken(stock) : false;
      });
      const activeThemeUptrend = isThemeUptrend(activeTheme);
      const shouldExit = sidecarTriggered || lossTriggered || heldStockMaBroken || maRollingOver || isCloseWindow;
      const canEnter = activeThemeUptrend && !maRollingOver && !isCloseWindow && isMarketSession;
      const currentSymbols = positions.map((position) => position.symbol).sort().join(",");
      const targetSymbols = targetStocks.map((stock) => stock.symbol).sort().join(",");

      if (positions.length && (shouldExit || currentSymbols !== targetSymbols)) {
        setCash(portfolioValue);
        setPositions([]);
        setTradeLog((log) => [
          `${new Date().toLocaleTimeString("en-GB")} SELL ${
            sidecarTriggered
              ? "sidecar"
              : lossTriggered
                ? "stop-loss"
                : heldStockMaBroken
                  ? "holding MA break"
                  : isCloseWindow
                    ? "pre-close"
                    : maRollingOver
                      ? "theme MA rollover"
                      : "rotation"
          } ${formatMoney(portfolioValue)} net of fees`,
          ...log.slice(0, 5),
        ]);
        if (sidecarTriggered) {
          const message = `사이드카: 보유금액 5% 이상 손실 감지, 전량 매도 ${formatMoney(portfolioValue)}`;

          setSidecarAlert(message);
          setAutoRun(false);
          setStatusMessage(message);
        } else {
          setStatusMessage(
            lossTriggered
              ? "2% 손절 매도 실행"
              : heldStockMaBroken
                ? "보유 종목 MA 꺾임 매도"
                : isCloseWindow
                  ? "장마감 5분 전 청산"
                  : "테마 이동평균 꺾임 매도",
          );
        }
        return;
      }

      if (!positions.length && cash > 1000 && canEnter) {
        const nextPositions = buildBalancedPaperPositions(targetStocks, cash);
        const investedCash = nextPositions.reduce((sum, position) => sum + position.entryValue, 0);

        if (!nextPositions.length) {
          setStatusMessage("배정 현금으로 1주 이상 매수 가능한 TOP3 종목이 없습니다");
          return;
        }

        setCash(Math.max(0, cash - investedCash));
        setPositions(nextPositions);
        setSidecarAlert("");
        setTradeLog((log) => [
          `${new Date().toLocaleTimeString("en-GB")} BUY ${themeName(activeTheme, language)} TOP3 fee ${formatMoney(
            nextPositions.reduce((sum, position) => sum + position.entryFee, 0),
          )}`,
          ...log.slice(0, 5),
        ]);
        setStatusMessage(`${themeName(activeTheme, language)} TOP3 자동 진입`);
        return;
      }

      if (!positions.length && cash > 1000 && !canEnter) {
        setStatusMessage(
          !activeThemeUptrend
            ? "1위 테마가 상승 추세가 아니라 신규 매수 대기"
            : maRollingOver
              ? "이동평균 회복 대기 중"
              : "장마감 5분 전 신규 진입 중지",
        );
      }
    }, 0);

    return () => window.clearTimeout(timeoutId);
  }, [activeTheme, autoRun, cash, language, positions, stocks, targetStocks, tick, dataStatus, marketStocks, marketScope]);

  const watchedStocks = watchlist
    .map((symbol) => stocks.find((stock) => stock.symbol === symbol))
    .filter((stock): stock is Stock => Boolean(stock))
    .filter((stock) => stock.region === marketScope);
  const tradingMarketLabel = marketScope === "domestic" ? "Domestic paper" : `Overseas paper · FX ${selectedStock.fxRate ?? "pending"}`;
  const tradingCostText = tradingCostLabel(marketScope);
  const accountValue = positions.reduce((sum, position) => {
    const stock = stocks.find((item) => item.symbol === position.symbol);
    return sum + liquidationValue(position, stock);
  }, cash);
  const portfolioFresh = dataStatus === "ready" && positions.every(p => stocks.some(s => s.symbol === p.symbol && quoteFresh(s)));
  useEffect(() => { latestPortfolio.current = { value: accountValue, fresh: portfolioFresh, syncedAt: lastQuoteSync }; }, [accountValue, portfolioFresh, lastQuoteSync]);
  const profitValues = profitPoints.map(point => point.value);
  const flatProfit = profitValues.every(value => value === 0);
  const profitMin = Math.min(flatProfit ? -1 : 0, ...profitValues);
  const profitMax = Math.max(flatProfit ? 1 : 0, ...profitValues);
  const profitSpread = profitMax - profitMin || 1;
  const profitPath = profitPoints.map((point, index) => `${index ? "L" : "M"} ${50 + (point.timestamp - (profitPoints[0]?.timestamp ?? point.timestamp)) / Math.max(1, (profitPoints.at(-1)?.timestamp ?? point.timestamp) - (profitPoints[0]?.timestamp ?? point.timestamp)) * 760} ${40 + (profitMax - point.value) / profitSpread * 250}`).join(" ");
  const activeThemeIsUptrend = activeTheme ? isThemeUptrend(activeTheme) : false;
  const pnl = accountValue - paperInitialCash;
  const pnlRate = (pnl / paperInitialCash) * 100;
  const dataModeLabel = apiBlocked
    ? "API paused"
    : dataStatus === "loading"
      ? t.loadingQuotes
      : dataStatus === "error"
        ? t.quoteError
        : stocks.some((stock) => stock.source)
          ? t.liveDataMode
          : t.dataMode;
  const marketFeed = [
    {
      label: "Toss",
      value: brokerConfigured ? "30s polling" : "Setup required",
      change: dataStatus === "ready" ? "CONNECTED" : "PENDING",
      positive: dataStatus === "ready",
    },
    {
      label: activeTheme ? themeName(activeTheme, language) : "-",
      value: `${(activeTheme ? themeMomentum(activeTheme) : 0).toFixed(2)} MA`,
      change: activeThemeIsUptrend ? "UPTREND" : "WAIT",
      positive: activeThemeIsUptrend,
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
  ];

  function selectMarket(nextScope: MarketScope) {
    const firstStock = stocks.find((stock) => stock.region === nextScope);

    if (autoRun || positions.length) { setStatusMessage("Stop and reset the paper session before changing markets"); return; }
    setMarketScope(nextScope);
    setSelectedSymbol(firstStock?.symbol ?? selectedSymbol);
    setQuery("");
  }

  function toggleWatchlist(symbol: string) {
    setWatchlist((currentWatchlist) =>
      currentWatchlist.includes(symbol)
        ? currentWatchlist.filter((watchSymbol) => watchSymbol !== symbol)
        : [...currentWatchlist, symbol],
    );
  }

  function resetSimulation() {
    const parsedInputCash = Number(paperCashInput);
    const nextInitialCash = Math.max(1_000_000, Math.round(Number.isFinite(parsedInputCash) ? parsedInputCash : defaultPaperCash));

    setAutoRun(false);
    setProfitPoints([]);
    setPaperInitialCash(nextInitialCash);
    setPaperCashInput(String(nextInitialCash));
    setCash(nextInitialCash);
    setPositions([]);
    setSidecarAlert("");
    setTradeLog([`Reset: ${nextInitialCash.toLocaleString("en-US")} KRW paper account`]);
    setStatusMessage(`모의 계좌를 ${formatMoney(nextInitialCash)}으로 초기화`);
  }

  function focusTheme(theme: ThemeUniverse) {
    const firstStock = theme.stocks[0];

    if (!firstStock) {
      return;
    }

    if (theme.region !== marketScope && (autoRun || positions.length)) { setStatusMessage("Stop and reset before changing markets"); return; }
    setMarketScope(theme.region);
    setSelectedSymbol(firstStock.symbol);
    setQuery("");
    setStatusMessage(`${themeName(theme, language)} TOP5 selected`);
  }

  function handleUniverseModeChange(nextMode: UniverseMode) {
    if (nextMode === universeMode) {
      return;
    }

    if (autoRun || positions.length) { setStatusMessage("Stop and reset the paper session before changing universe modes"); return; }
    setUniverseMode(nextMode);
    setQuery("");
    setStatusMessage(nextMode === "core" ? "코어 테마만 표시" : "확장 테마까지 표시");
  }

  function handleUniverseRefresh() {
    if (apiBlocked) {
      clearApiBlock();
      setStatusMessage("Retrying data feeds...");
    }

    const now = Date.now();

    if (now < themeRefreshBlockedUntil) {
      const waitSeconds = Math.ceil((themeRefreshBlockedUntil - now) / 1000);
      const message = `테마 TOP5 갱신 대기: ${waitSeconds}초 후 재시도`;

      setThemeRefreshMessage(message);
      setStatusMessage(message);
      return;
    }

    setThemeRefreshBlockedUntil(now + themeRefreshCooldownMs);
    setUniverseRefreshKey((currentKey) => currentKey + 1);
  }

  function toggleAutomation(running: boolean) {
    if (running && !profitPoints.length) {
      sessionBaseline.current = accountValue;
      setProfitPoints([{ timestamp: Date.now(), value: 0 }]);
    }
    setAutoRun(running);
  }

  async function verifyConnection() {
    setConnectionBusy(true);
    try {
      const response = await fetch(`${apiBaseUrl}/brokers/toss/connection`);
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? "Connection failed");
      setBrokerStatus(`Connected · ${payload.accounts.length} account(s) · local paper orders`);
    } catch (error) { setBrokerStatus(error instanceof Error ? error.message : "Connection failed"); }
    finally { setConnectionBusy(false); }
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
          <small>{brokerStatus}</small>
          <button type="button" disabled={!brokerConfigured || connectionBusy} onClick={verifyConnection}>{connectionBusy ? "Connecting…" : "Verify Toss connection"}</button>
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
                setStatusMessage("Settings: 30s quotes / 5s profit samples / TOP3 paper / 2% stop / 5% sidecar");
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
          <div className={styles.themeModeTabs} aria-label="Theme universe mode">
            {(["core", "all"] as UniverseMode[]).map((mode) => (
              <button
                className={mode === universeMode ? styles.themeModeTabActive : styles.themeModeTab}
                data-testid={`theme-mode-${mode}`}
                key={mode}
                type="button"
                onClick={() => handleUniverseModeChange(mode)}
              >
                {mode === "core" ? t.themeModeCore : t.themeModeAll}
              </button>
            ))}
          </div>
          <div className={styles.marketStatus}>
            <span>{t.market}</span>
            <strong>
              <span aria-hidden="true" />
              {dataStatus === "ready" ? "Data connected" : "Pending"}
            </strong>
            <small>{dataModeLabel}</small>
              <button
                className={styles.refreshButton}
                type="button"
                onClick={() => {
                  clearApiBlock();
                  setRefreshKey((currentKey) => currentKey + 1);
                }}
                aria-label={t.refreshQuotes}
              >
              <RefreshCw size={14} />
            </button>
            <button
              className={styles.universeRefreshButton}
              data-testid="universe-refresh"
              disabled={themeRefreshStatus === "loading"}
              type="button"
              onClick={handleUniverseRefresh}
            >
              {t.refreshThemes}
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
              {filteredThemeGroups.length ? (
                filteredThemeGroups.map((group) => (
                  <section className={styles.stockThemeGroup} key={group.theme.id}>
                    <button className={styles.stockThemeHeader} type="button" onClick={() => focusTheme(group.theme)}>
                      <span>{themeName(group.theme, language)}</span>
                      <strong>{themeMomentum(group.theme).toFixed(2)} MA</strong>
                    </button>
                    {group.stocks.map((stock) => (
                      <button
                        className={`${styles.stockRow} ${stock.symbol === selectedStock.symbol ? styles.stockRowSelected : ""}`}
                        key={stock.symbol}
                        type="button"
                        onClick={() => {
                          setSelectedSymbol(stock.symbol);
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
                          <b>{stock.source ? formatPrice(stock) : "Awaiting Toss"}</b>
                          <small className={stock.change >= 0 ? styles.positive : styles.negative}>
                            {stock.change >= 0 ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                            {stock.change > 0 ? "+" : ""}
                            {stock.source ? stock.change.toFixed(2) : "—"}%
                          </small>
                        </span>
                      </button>
                    ))}
                  </section>
                ))
              ) : (
                <p className={styles.emptyState}>{t.noMatches}</p>
              )}
            </div>
          </div>

          <div className={styles.chartPanel}>
            <div className={styles.chartHeader}>
              <div><span>Toss Securities · local paper trading</span><h2>Session profit</h2></div>
              <button className={styles.watchButton} type="button" onClick={() => toggleWatchlist(selectedStock.symbol)}><Star size={17} />{selectedStock.symbol}</button>
            </div>
            <div className={styles.quoteStrip}>
              <div><span>Profit since start</span><strong data-testid="session-profit">{formatMoney(profitPoints.at(-1)?.value ?? 0)}</strong></div>
              <div><span>Paper equity</span><strong>{formatMoney(accountValue)}</strong></div>
              <div><span>Sampling / market data</span><strong>5s / 30s</strong></div>
              <div><span>Status</span><strong>{autoRun ? "Running" : profitPoints.length ? "Paused" : "Not started"}</strong></div>
            </div>
            <div className={styles.sourceMeta}><span>{brokerStatus}</span><span>{portfolioFresh ? "Latest snapshot · prices refreshed every 30s, FX every 5m" : "Waiting for valid quotes — sampling suspended"}</span></div>
            {profitPoints.length ? (
              <div className={styles.profitCanvas}>
                <svg role="img" aria-label="Paper trading session profit chart" data-testid="profit-chart" viewBox="0 0 900 350">
                  {[0, 1, 2, 3, 4].map(index => <g key={index}><line className={styles.gridLine} x1="50" x2="810" y1={40 + index * 62.5} y2={40 + index * 62.5} /><text className={styles.axisLabel} x="820" y={44 + index * 62.5}>{(profitMax - index * profitSpread / 4).toLocaleString("en-US", { maximumFractionDigits: profitSpread < 10 ? 1 : 0 })}</text></g>)}
                  <path className={styles.profitLine} d={profitPath} />
                  {profitPoints.length === 1 && <circle cx="50" cy="165" r="4" fill="#2dd4bf" />}
                  <text className={styles.axisLabel} x="50" y="330">{new Date(profitPoints[0].timestamp).toLocaleTimeString("en-GB")}</text>
                  <text className={styles.axisLabel} x="810" y="330" textAnchor="end">{new Date(profitPoints.at(-1)!.timestamp).toLocaleTimeString("en-GB")}</text>
                </svg>
                <p data-testid="profit-samples">{profitPoints.length} samples · KRW · net of estimated commissions</p>
              </div>
            ) : <div className={styles.profitEmpty} data-testid="profit-empty"><Bot size={36} /><h3>Your session starts here</h3><p>Start paper automation to record profit every 5 seconds.</p></div>}
            <div className={styles.sourceMeta}><span>{statusMessage}</span><span>Stop retains history. Reset clears the session. Browser reload clears paper state.</span></div>
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
                    {stock.source ? stock.change.toFixed(2) : "—"}%
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
                <label className={styles.capitalInput}>
                  <span>Paper capital</span>
                  <input
                    data-testid="paper-cash-input"
                    inputMode="numeric"
                    min={1_000_000}
                    step={1_000_000}
                    type="number"
                    value={paperCashInput}
                    onChange={(event) => {
                      setPaperCashInput(event.currentTarget.value);
                    }}
                  />
                </label>
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
                <div>
                  <span>Market</span>
                  <strong>{tradingMarketLabel}</strong>
                </div>
                <div>
                  <span>Trading cost</span>
                  <strong>{tradingCostText}</strong>
                </div>
              </div>
              <div className={styles.simActions}>
                <label className={styles.autoToggle}>
                  <input
                    checked={autoRun}
                    data-testid="auto-run-toggle"
                    disabled={!autoRun && (!brokerConfigured || dataStatus !== "ready")}
                    onChange={(event) => toggleAutomation(event.currentTarget.checked)}
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
              {sidecarAlert ? (
                <div className={styles.sidecarAlert} data-testid="sidecar-alert">
                  <Bell size={15} />
                  <span>{sidecarAlert}</span>
                </div>
              ) : null}
              <div className={styles.ruleList}>
                <span>Commission estimates exclude taxes and other charges.</span>
                <span>Strategy requires actual Toss minute/daily history; no sample orders.</span>
                <span>MA exit: 0.4% spread + 0.25% decline + 4/5 weak leaders</span>
                <span>{t.activeTheme}: {activeTheme ? themeName(activeTheme, language) : "-"}</span>
                <span>Leading theme uptrend: {activeThemeIsUptrend ? "Pass" : "Wait"}</span>
                <span>{tradingMarketLabel}</span>
                <span>Balanced TOP3 · whole shares only</span>
                <span>{t.stopLoss}</span>
                <span>Commission estimate {tradingCostText}</span>
                <span>{t.exitRule}</span>
              </div>
              <div className={styles.positionList}>
                {positions.length ? (
                  positions.map((position) => {
                    const stock = stocks.find((item) => item.symbol === position.symbol);
                    const value = liquidationValue(position, stock);
                    const positionPnl = value - position.entryValue;

                    return (
                      <button
                        className={styles.positionRow}
                        key={position.symbol}
                        type="button"
                        onClick={() => {
                          if (!stock) {
                            return;
                          }

                          setMarketScope(stock.region);
                          setSelectedSymbol(stock.symbol);
                                                setStatusMessage(`${stockName(stock, language)} position selected`);
                        }}
                      >
                        <strong>
                          {position.symbol}
                          <small>{stock ? stockName(stock, language) : "Unknown"}</small>
                        </strong>
                        <span>
                          {position.shares.toLocaleString("ko-KR")}주 · {formatMoney(value)}
                          <small className={positionPnl >= 0 ? styles.positive : styles.negative}>
                            {positionPnl >= 0 ? "+" : ""}
                            {formatMoney(positionPnl)}
                          </small>
                        </span>
                      </button>
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
                    <small>{stock.change > 0 ? "+" : ""}{stock.source ? stock.change.toFixed(2) : "—"}%</small>
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
            <div className={styles.themeRefreshMeta} data-testid="theme-refresh-meta">
              <span>{universeMode === "core" ? "Core 6" : `Extended ${universes.length}`}</span>
              <strong>{themeRefreshStatus === "loading" ? "Refreshing" : themeRefreshMessage}</strong>
              <small>{lastThemeRefreshAt ? `${t.updated} ${lastThemeRefreshAt}` : "Manual refresh cooldown 60s"}</small>
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
