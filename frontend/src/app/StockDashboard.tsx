"use client";

import {
  AlertCircle,
  BarChart3,
  Bell,
  Briefcase,
  FileText,
  Home,
  LineChart,
  Plus,
  RefreshCw,
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
  signal: "Buy" | "Watch" | "Hold";
  strategy: string;
  series: Record<RangeKey, ChartPoint[]>;
};

type ChartPoint = {
  label: string;
  value: number;
  open: number;
  high: number;
  low: number;
  close: number;
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

type DataStatus = "idle" | "loading" | "ready" | "error";

type Candle = {
  label: string;
  open: number;
  high: number;
  low: number;
  close: number;
};

const ranges: RangeKey[] = ["LIVE", "1D", "1W", "1M", "1Y", "5Y", "ALL"];
const rangePointCounts: Record<RangeKey, number> = {
  LIVE: 48,
  "1D": 48,
  "1W": 35,
  "1M": 40,
  "1Y": 52,
  "5Y": 60,
  ALL: 72,
};

const copy = {
  en: {
    appName: "Money Copy Bot",
    appSubtitle: "Stock research and automation cockpit",
    domestic: "Domestic",
    overseas: "Overseas",
    searchTitle: "Stock search",
    searchDescription: "Search by symbol, company, market, or sector.",
    searchPlaceholder: "Search AAPL, 005930, semiconductor...",
    language: "Language",
    market: "Market",
    open: "Open",
    dataMode: "Sample data",
    liveDataMode: "KIS live quotes",
    loadingQuotes: "Loading quotes",
    quoteError: "Quote sync error",
    refreshQuotes: "Refresh quotes",
    updated: "Updated",
    deskMode: "Research desk",
    rangeMove: "Range move",
    rangeHigh: "Range high",
    rangeLow: "Range low",
    executionMode: "Execution",
    paperOnly: "Paper only",
    signalQueue: "Signal queue",
    dataBridge: "Data bridge",
    manualReview: "Manual review",
    home: "Home",
    portfolio: "Portfolio",
    signals: "Signals",
    automation: "Automation",
    backtest: "Backtest",
    reports: "Reports",
    settings: "Settings",
    broker: "Broker",
    demoAccount: "Demo Account",
    connected: "Connected",
    buyingPower: "Buying Power",
    results: "Results",
    symbols: "symbols",
    watchlist: "Watchlist",
    tracked: "tracked",
    lastPrice: "Last price",
    portfolioSignal: "Portfolio signal",
    sector: "Sector",
    addToWatchlist: "Add to watchlist",
    watching: "Watching",
    chartRange: "Chart range",
    chartType: "Chart type",
    candle: "Candles",
    line: "Line",
    rangeLabels: {
      LIVE: "Today live",
      "1D": "1D",
      "1W": "1W",
      "1M": "1M",
      "1Y": "1Y",
      "5Y": "5Y",
      ALL: "All",
    },
    point: "Point",
    researchNotes: "Research & Notes",
    portfolioSignalPanel: "Portfolio signal",
    sentiment: "Momentum score",
    topSignals: "Top signals",
    viewAll: "View all",
    automationPreview: "Automation preview",
    automationText: "Next step: connect brokerage APIs and replace sample data with live quotes.",
    noMatches: "No matching symbols",
  },
  ko: {
    appName: "Money Copy Bot",
    appSubtitle: "\uC8FC\uC2DD \uB9AC\uC11C\uCE58\uC640 \uC790\uB3D9\uB9E4\uB9E4 \uC791\uC5C5\uC2E4",
    domestic: "\uAD6D\uB0B4",
    overseas: "\uD574\uC678",
    searchTitle: "\uC885\uBAA9 \uAC80\uC0C9",
    searchDescription: "\uD2F0\uCEE4, \uD68C\uC0AC\uBA85, \uC2DC\uC7A5, \uC139\uD130\uB85C \uAC80\uC0C9",
    searchPlaceholder: "AAPL, 005930, semiconductor...",
    language: "\uC5B8\uC5B4",
    market: "\uC2DC\uC7A5",
    open: "\uC5F4\uB9BC",
    dataMode: "\uC0D8\uD50C \uB370\uC774\uD130",
    liveDataMode: "KIS \uC2E4\uC81C \uC2DC\uC138",
    loadingQuotes: "\uC2DC\uC138 \uBD88\uB7EC\uC624\uB294 \uC911",
    quoteError: "\uC2DC\uC138 \uC5F0\uB3D9 \uC624\uB958",
    refreshQuotes: "\uC2DC\uC138 \uC0C8\uB85C\uACE0\uCE68",
    updated: "\uAC31\uC2E0",
    deskMode: "\uB9AC\uC11C\uCE58 \uB370\uC2A4\uD06C",
    rangeMove: "\uAE30\uAC04 \uB4F1\uB77D",
    rangeHigh: "\uAE30\uAC04 \uACE0\uAC00",
    rangeLow: "\uAE30\uAC04 \uC800\uAC00",
    executionMode: "\uC2E4\uD589 \uBAA8\uB4DC",
    paperOnly: "\uBAA8\uC758 \uC804\uC6A9",
    signalQueue: "\uC2DC\uADF8\uB110 \uD050",
    dataBridge: "\uB370\uC774\uD130 \uBE0C\uB9AC\uC9C0",
    manualReview: "\uC218\uB3D9 \uAC80\uD1A0",
    home: "\uD648",
    portfolio: "\uD3EC\uD2B8\uD3F4\uB9AC\uC624",
    signals: "\uC2DC\uADF8\uB110",
    automation: "\uC790\uB3D9\uD654",
    backtest: "\uBC31\uD14C\uC2A4\uD2B8",
    reports: "\uB9AC\uD3EC\uD2B8",
    settings: "\uC124\uC815",
    broker: "\uC99D\uAD8C\uC0AC",
    demoAccount: "\uB370\uBAA8 \uACC4\uC88C",
    connected: "\uC5F0\uACB0\uB428",
    buyingPower: "\uB9E4\uC218 \uAC00\uB2A5\uAE08\uC561",
    results: "\uAC80\uC0C9 \uACB0\uACFC",
    symbols: "\uC885\uBAA9",
    watchlist: "\uAD00\uC2EC\uC885\uBAA9",
    tracked: "\uAC1C \uCD94\uC801",
    lastPrice: "\uD604\uC7AC\uAC00",
    portfolioSignal: "\uD3EC\uD2B8\uD3F4\uB9AC\uC624 \uC2DC\uADF8\uB110",
    sector: "\uC139\uD130",
    addToWatchlist: "\uAD00\uC2EC\uC885\uBAA9 \uCD94\uAC00",
    watching: "\uAD00\uC2EC\uC885\uBAA9",
    chartRange: "\uCC28\uD2B8 \uAE30\uAC04",
    chartType: "\uCC28\uD2B8 \uC720\uD615",
    candle: "\uBD09\uCC28\uD2B8",
    line: "\uC120\uCC28\uD2B8",
    rangeLabels: {
      LIVE: "\uC624\uB298 \uC2E4\uC2DC\uAC04",
      "1D": "1D",
      "1W": "1W",
      "1M": "1M",
      "1Y": "1Y",
      "5Y": "5Y",
      ALL: "\uC804\uCCB4",
    },
    point: "\uC9C0\uC810",
    researchNotes: "\uB9AC\uC11C\uCE58 & \uB178\uD2B8",
    portfolioSignalPanel: "\uD3EC\uD2B8\uD3F4\uB9AC\uC624 \uC2DC\uADF8\uB110",
    sentiment: "\uBAA8\uBA58\uD140 \uC810\uC218",
    topSignals: "\uC8FC\uC694 \uC2DC\uADF8\uB110",
    viewAll: "\uC804\uCCB4 \uBCF4\uAE30",
    automationPreview: "\uC790\uB3D9\uD654 \uBBF8\uB9AC\uBCF4\uAE30",
    automationText:
      "\uB2E4\uC74C \uB2E8\uACC4: \uC99D\uAD8C\uC0AC API\uB97C \uC5F0\uACB0\uD558\uACE0 \uC0D8\uD50C \uB370\uC774\uD130\uB97C \uC2E4\uC2DC\uAC04 \uC2DC\uC138\uB85C \uAD50\uCCB4\uD569\uB2C8\uB2E4.",
    noMatches: "\uAC80\uC0C9 \uACB0\uACFC \uC5C6\uC74C",
  },
} as const;

function formatClock(totalMinutes: number) {
  const hours = Math.floor(totalMinutes / 60);
  const minutes = Math.round(totalMinutes % 60);

  return `${hours.toString().padStart(2, "0")}:${minutes.toString().padStart(2, "0")}`;
}

function pointLabel(range: RangeKey, index: number, count: number) {
  if (range === "LIVE" || range === "1D") {
    const start = 9 * 60 + 30;
    const end = 16 * 60;
    const totalMinutes = start + ((end - start) * index) / Math.max(count - 1, 1);

    return formatClock(totalMinutes);
  }

  if (range === "1W") {
    const days = ["Mon", "Tue", "Wed", "Thu", "Fri"];
    const day = days[Math.min(days.length - 1, Math.floor((index / count) * days.length))];
    const start = 9 * 60 + 30;
    const end = 16 * 60;
    const dayProgress = (index % Math.ceil(count / days.length)) / Math.ceil(count / days.length);

    return `${day} ${formatClock(start + (end - start) * dayProgress)}`;
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

function interpolate(values: number[], ratio: number) {
  const scaledIndex = ratio * (values.length - 1);
  const leftIndex = Math.floor(scaledIndex);
  const rightIndex = Math.min(values.length - 1, leftIndex + 1);
  const localRatio = scaledIndex - leftIndex;

  return values[leftIndex] + (values[rightIndex] - values[leftIndex]) * localRatio;
}

function baseValuesForRange(values: number[], range: RangeKey) {
  const first = values[0];
  const last = values[values.length - 1];
  const direction = last >= first ? 1 : -1;
  const spread = Math.max(Math.abs(last - first), Math.abs(last) * 0.012, 1);

  if (range === "LIVE") {
    return values;
  }

  const multipliers: Record<Exclude<RangeKey, "LIVE">, { start: number; step: number }> = {
    "1D": { start: 0.08, step: 0 },
    "1W": { start: -0.22, step: 0.055 },
    "1M": { start: -0.72, step: 0.15 },
    "1Y": { start: -1.85, step: 0.36 },
    "5Y": { start: -4.6, step: 0.82 },
    ALL: { start: -7.4, step: 1.22 },
  };
  const multiplier = multipliers[range];

  return values.map(
    (value, index) => value + direction * spread * multiplier.start + index * direction * spread * multiplier.step,
  );
}

function buildChartPoints(values: number[], range: RangeKey): ChartPoint[] {
  const count = rangePointCounts[range];
  const first = values[0];
  const last = values[values.length - 1];
  const spread = Math.max(Math.abs(last - first), Math.abs(last) * 0.01, 1);

  return Array.from({ length: count }, (_, index) => {
    const ratio = index / Math.max(count - 1, 1);
    const base = interpolate(values, ratio);
    const wave =
      index === 0 || index === count - 1
        ? 0
        : Math.sin(index * 0.92 + range.length) * spread * 0.11 +
          Math.sin(index * 0.31) * spread * 0.07;
    const close = base + wave;
    const previousClose = index === 0 ? close - spread * 0.025 : interpolate(values, (index - 1) / count);
    const open = index === 0 ? close - spread * 0.018 : previousClose + wave * 0.18;
    const bodySpread = Math.abs(close - open);
    const wickSpread = Math.max(Math.abs(close) * 0.0016, bodySpread * 0.58, spread * 0.035);
    const high = Math.max(open, close) + wickSpread * (0.55 + (index % 4) * 0.12);
    const low = Math.min(open, close) - wickSpread * (0.54 + (index % 3) * 0.11);

    return {
      label: pointLabel(range, index, count),
      value: close,
      open,
      high,
      low,
      close,
    };
  });
}

function makeSeries(values: number[]): Record<RangeKey, ChartPoint[]> {
  return {
    LIVE: buildChartPoints(baseValuesForRange(values, "LIVE"), "LIVE"),
    "1D": buildChartPoints(baseValuesForRange(values, "1D"), "1D"),
    "1W": buildChartPoints(baseValuesForRange(values, "1W"), "1W"),
    "1M": buildChartPoints(baseValuesForRange(values, "1M"), "1M"),
    "1Y": buildChartPoints(baseValuesForRange(values, "1Y"), "1Y"),
    "5Y": buildChartPoints(baseValuesForRange(values, "5Y"), "5Y"),
    ALL: buildChartPoints(baseValuesForRange(values, "ALL"), "ALL"),
  };
}

const fallbackStocks: Stock[] = [
  {
    symbol: "NVDA",
    name: "NVIDIA Corp.",
    localName: "\uC5D4\uBE44\uB514\uC544",
    market: "NASDAQ",
    region: "overseas",
    currency: "USD",
    price: 214.75,
    change: -3.62,
    changeAmount: -8.07,
    sector: "Semiconductors",
    sectorKo: "\uBC18\uB3C4\uCCB4",
    signal: "Watch",
    strategy: "Momentum",
    series: makeSeries([222.82, 220.5, 218.1, 216.2, 215.8, 214.9, 214.75]),
  },
  {
    symbol: "MU",
    name: "Micron Technology Inc.",
    localName: "\uB9C8\uC774\uD06C\uB860",
    market: "NASDAQ",
    region: "overseas",
    currency: "USD",
    price: 1079.57,
    change: 1.45,
    changeAmount: 15.47,
    sector: "Memory Chips",
    sectorKo: "\uBA54\uBAA8\uB9AC \uBC18\uB3C4\uCCB4",
    signal: "Hold",
    strategy: "Memory Cycle",
    series: makeSeries([1064.1, 1068.2, 1071.4, 1077.6, 1082.8, 1075.4, 1079.57]),
  },
  {
    symbol: "SNDK",
    name: "Sandisk Corp.",
    localName: "\uC0CC\uB514\uC2A4\uD06C",
    market: "NASDAQ",
    region: "overseas",
    currency: "USD",
    price: 1831.5,
    change: 6.71,
    changeAmount: 115.14,
    sector: "Storage",
    sectorKo: "\uC2A4\uD1A0\uB9AC\uC9C0",
    signal: "Buy",
    strategy: "NAND Supply",
    series: makeSeries([1716.36, 1744.8, 1761.2, 1805.4, 1842.6, 1824.2, 1831.5]),
  },
  {
    symbol: "005930",
    name: "Samsung Electronics",
    localName: "\uC0BC\uC131\uC804\uC790",
    market: "KOSPI",
    region: "domestic",
    currency: "KRW",
    price: 355500,
    change: -1.39,
    changeAmount: -5000,
    sector: "Semiconductors",
    sectorKo: "\uBC18\uB3C4\uCCB4",
    signal: "Watch",
    strategy: "Cycle Recovery",
    series: makeSeries([360500, 349000, 348000, 356000, 366000, 360000, 355500]),
  },
  {
    symbol: "000660",
    name: "SK Hynix",
    localName: "SK\uD558\uC774\uB2C9\uC2A4",
    market: "KOSPI",
    region: "domestic",
    currency: "KRW",
    price: 2293000,
    change: -2.84,
    changeAmount: -67000,
    sector: "Memory Chips",
    sectorKo: "\uBA54\uBAA8\uB9AC \uBC18\uB3C4\uCCB4",
    signal: "Watch",
    strategy: "Momentum",
    series: makeSeries([2360000, 2284000, 2262000, 2295000, 2327000, 2310000, 2293000]),
  },
];

const initialWatchlist = ["NVDA", "MU", "SNDK", "005930", "000660"];
const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

function stockSignal(change: number): Stock["signal"] {
  if (change >= 2) {
    return "Buy";
  }

  if (change <= -1) {
    return "Watch";
  }

  return "Hold";
}

function buildLiveSeries(quote: KisQuote) {
  const previousClose = quote.price - quote.change_amount;
  const open = quote.open ?? previousClose;
  const high = quote.high ?? Math.max(previousClose, quote.price) * 1.006;
  const low = quote.low ?? Math.min(previousClose, quote.price) * 0.994;

  return makeSeries([
    previousClose,
    open,
    low,
    (open + quote.price) / 2,
    high,
    quote.price - quote.change_amount * 0.18,
    quote.price,
  ]);
}

function stockFromKisQuote(quote: KisQuote): Stock {
  return {
    symbol: quote.symbol,
    name: quote.name,
    localName: quote.local_name,
    market: quote.market,
    region: quote.region,
    currency: quote.currency,
    price: quote.price,
    change: quote.change,
    changeAmount: quote.change_amount,
    open: quote.open,
    high: quote.high,
    low: quote.low,
    volume: quote.volume,
    fetchedAt: quote.fetched_at,
    source: quote.source,
    sector: quote.sector,
    sectorKo: quote.sector_ko,
    signal: stockSignal(quote.change),
    strategy: "KIS Quote Sync",
    series: buildLiveSeries(quote),
  };
}

function formatCompactNumber(value: number | null | undefined, language: Language) {
  if (!value) {
    return "-";
  }

  return value.toLocaleString(language === "ko" ? "ko-KR" : "en-US", {
    maximumFractionDigits: 0,
  });
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

function stockName(stock: Stock, language: Language) {
  return language === "ko" ? stock.localName : stock.name;
}

function sectorName(stock: Stock, language: Language) {
  return language === "ko" ? stock.sectorKo : stock.sector;
}

function signalLabel(signal: Stock["signal"], language: Language) {
  if (language === "en") {
    return signal;
  }

  return {
    Buy: "\uB9E4\uC218",
    Watch: "\uAD00\uCC30",
    Hold: "\uBCF4\uC720",
  }[signal];
}

function formatPrice(stock: Stock) {
  if (stock.currency === "KRW") {
    return `${stock.price.toLocaleString("ko-KR")} KRW`;
  }

  return `$${stock.price.toLocaleString("en-US", {
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
  })}`;
}

function xFor(index: number, count: number, width: number, padding: number) {
  return padding + (index / Math.max(count - 1, 1)) * (width - padding * 2);
}

function buildPath(
  points: ChartPoint[],
  width: number,
  height: number,
  padding: number,
  min: number,
  max: number,
) {
  const spread = max - min || 1;

  return points
    .map((point, index) => {
      const x = xFor(index, points.length, width, padding);
      const y = padding + ((max - point.value) / spread) * (height - padding * 2);

      return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
}

function pointFor(
  points: ChartPoint[],
  index: number,
  width: number,
  height: number,
  padding: number,
  min: number,
  max: number,
) {
  const spread = max - min || 1;
  const x = xFor(index, points.length, width, padding);
  const y = padding + ((max - points[index].value) / spread) * (height - padding * 2);

  return { x, y };
}

function buildCandles(points: ChartPoint[]): Candle[] {
  return points.map((point) => {
    return {
      label: point.label,
      open: point.open,
      high: point.high,
      low: point.low,
      close: point.close,
    };
  });
}

function yFor(value: number, min: number, max: number, height: number, padding: number) {
  const spread = max - min || 1;

  return padding + ((max - value) / spread) * (height - padding * 2);
}

function axisTickIndexes(count: number) {
  const tickCount = 6;
  const step = Math.max(1, Math.floor((count - 1) / (tickCount - 1)));
  const indexes = Array.from({ length: tickCount }, (_, index) =>
    Math.min(count - 1, index * step),
  );

  return [...new Set([...indexes, count - 1])];
}

function formatAxisPrice(value: number, currency: Stock["currency"]) {
  if (currency === "KRW") {
    return Math.round(value).toLocaleString("ko-KR");
  }

  return value.toLocaleString("en-US", {
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
  });
}

export default function StockDashboard() {
  const [query, setQuery] = useState("");
  const [marketScope, setMarketScope] = useState<MarketScope>("overseas");
  const [language, setLanguage] = useState<Language>("ko");
  const [selectedSymbol, setSelectedSymbol] = useState("NVDA");
  const [watchlist, setWatchlist] = useState(initialWatchlist);
  const [range, setRange] = useState<RangeKey>("LIVE");
  const [chartType, setChartType] = useState<ChartType>("candle");
  const [activePoint, setActivePoint] = useState<number | null>(null);
  const [liveStocks, setLiveStocks] = useState<Stock[]>([]);
  const [dataStatus, setDataStatus] = useState<DataStatus>("idle");
  const [dataError, setDataError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);

  const t = copy[language];
  const stocks = liveStocks.length ? liveStocks : fallbackStocks;
  const marketStocks = useMemo(
    () => stocks.filter((stock) => stock.region === marketScope),
    [marketScope, stocks],
  );
  const filteredStocks = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();

    if (!normalizedQuery) {
      return marketStocks;
    }

    return marketStocks.filter((stock) =>
      [stock.symbol, stock.name, stock.localName, stock.market, stock.sector, stock.sectorKo].some(
        (value) => value.toLowerCase().includes(normalizedQuery),
      ),
    );
  }, [marketStocks, query]);

  useEffect(() => {
    const controller = new AbortController();

    async function loadQuotes() {
      setDataStatus((currentStatus) => (currentStatus === "idle" ? "loading" : currentStatus));
      setDataError("");

      try {
        const response = await fetch(`${apiBaseUrl}/quotes/kis/watchlist`, {
          signal: controller.signal,
        });

        if (!response.ok) {
          const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
          throw new Error(payload?.detail ?? `KIS quote request failed: ${response.status}`);
        }

        const payload = (await response.json()) as KisWatchlistResponse;
        const nextStocks = payload.data.map(stockFromKisQuote);

        if (nextStocks.length) {
          setLiveStocks(nextStocks);
          setDataStatus(payload.errors.length ? "error" : "ready");
          setDataError(payload.errors.join(" / "));
        } else {
          setDataStatus("error");
          setDataError(payload.errors.join(" / ") || "No KIS quote data returned.");
        }
      } catch (error) {
        if (controller.signal.aborted) {
          return;
        }

        setDataStatus("error");
        setDataError(error instanceof Error ? error.message : "KIS quote request failed.");
      }
    }

    loadQuotes();
    const intervalId = window.setInterval(loadQuotes, 30000);

    return () => {
      controller.abort();
      window.clearInterval(intervalId);
    };
  }, [refreshKey]);

  const selectedStock =
    stocks.find((stock) => stock.symbol === selectedSymbol && stock.region === marketScope) ??
    marketStocks[0];
  const selectedPoints = selectedStock.series[range];
  const selectedValues = selectedPoints.map((point) => point.value);
  const selectedCandles = buildCandles(selectedPoints);
  const selectedIndex = activePoint ?? selectedPoints.length - 1;
  const selectedPoint = selectedPoints[selectedIndex];
  const selectedPointValue = selectedPoint.value;
  const rangeStart = selectedValues[0];
  const rangeEnd = selectedValues[selectedValues.length - 1];
  const rangeMove = ((rangeEnd - rangeStart) / rangeStart) * 100;
  const rangeHigh = Math.max(...selectedValues);
  const rangeLow = Math.min(...selectedValues);
  const chartWidth = 820;
  const chartHeight = 340;
  const chartPadding = 28;
  const candleExtremes = selectedCandles.flatMap((candle) => [candle.high, candle.low]);
  const rawChartMin = Math.min(...selectedValues, ...candleExtremes);
  const rawChartMax = Math.max(...selectedValues, ...candleExtremes);
  const chartSpread = rawChartMax - rawChartMin || Math.abs(rangeEnd) * 0.01 || 1;
  const chartMin = rawChartMin - chartSpread * 0.1;
  const chartMax = rawChartMax + chartSpread * 0.1;
  const path = buildPath(selectedPoints, chartWidth, chartHeight, chartPadding, chartMin, chartMax);
  const xAxisIndexes = axisTickIndexes(selectedPoints.length);
  const yAxisTicks = [0, 1, 2, 3].map(
    (tick) => chartMax - ((chartMax - chartMin) * tick) / 3,
  );
  const candleWidth = Math.max(
    3,
    Math.min(9, ((chartWidth - chartPadding * 2) / selectedCandles.length) * 0.48),
  );
  const activeCoordinates = pointFor(
    selectedPoints,
    selectedIndex,
    chartWidth,
    chartHeight,
    chartPadding,
    chartMin,
    chartMax,
  );
  const watchedStocks = watchlist
    .map((symbol) => stocks.find((stock) => stock.symbol === symbol))
    .filter((stock): stock is Stock => Boolean(stock))
    .filter((stock) => stock.region === marketScope);
  const isWatched = watchlist.includes(selectedStock.symbol);
  const latestFetchedAt = stocks.find((stock) => stock.fetchedAt)?.fetchedAt;
  const dataModeLabel =
    dataStatus === "loading"
      ? t.loadingQuotes
      : dataStatus === "error"
        ? t.quoteError
        : liveStocks.length
          ? t.liveDataMode
          : t.dataMode;
  const marketFeed = [
    {
      label: "KIS",
      value: liveStocks.length ? `${liveStocks.length} synced` : "sample fallback",
      change: dataStatus === "error" ? "ERR" : "LIVE",
      positive: dataStatus !== "error",
    },
    ...stocks.slice(0, 2).map((stock) => ({
      label: stock.symbol,
      value: formatPrice(stock),
      change: `${stock.change > 0 ? "+" : ""}${stock.change.toFixed(2)}%`,
      positive: stock.change >= 0,
    })),
  ];
  const navItems = [
    { label: t.home, icon: Home },
    { label: t.portfolio, icon: Briefcase },
    { label: t.signals, icon: BarChart3 },
    { label: t.automation, icon: Zap },
    { label: t.backtest, icon: LineChart },
    { label: t.reports, icon: FileText },
    { label: t.settings, icon: Settings },
  ];

  function selectStock(symbol: string) {
    setSelectedSymbol(symbol);
    setActivePoint(null);
  }

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

  function handleChartPointerMove(event: React.PointerEvent<SVGSVGElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    const relativeX = event.clientX - rect.left;
    const ratio = Math.min(Math.max(relativeX / rect.width, 0), 1);
    const nextIndex = Math.round(ratio * (selectedValues.length - 1));

    setActivePoint(nextIndex);
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
          {navItems.map((item, index) => {
            const Icon = item.icon;

            return (
              <button
                className={index === 0 ? styles.navItemActive : styles.navItem}
                key={item.label}
                type="button"
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
            <strong>{marketScope === "domestic" ? "12,450,000 KRW" : "$42,880"}</strong>
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
            <span className={styles.productName}>MCBot</span>
            <h1>{t.appName}</h1>
          </div>
          <div className={styles.marketTicker} aria-label="Market overview">
            {marketFeed.map((feed) => (
              <div key={feed.label}>
                <span>{feed.label}</span>
                <strong>{feed.value}</strong>
                <small className={feed.positive ? styles.positive : styles.negative}>
                  {feed.change}
                </small>
              </div>
            ))}
          </div>
          <div className={styles.headerActions}>
            <label className={styles.languageSelect}>
              <span>{t.language}</span>
              <select
                value={language}
                onChange={(event) => setLanguage(event.target.value as Language)}
              >
                <option value="en">English</option>
                <option value="ko">{"\uD55C\uAD6D\uC5B4"}</option>
              </select>
            </label>
            <button className={styles.iconButton} type="button" aria-label="Notifications">
              <Bell size={18} />
            </button>
            <button className={styles.iconButton} type="button" aria-label="Settings">
              <Settings size={18} />
            </button>
          </div>
        </header>

        <section className={styles.controlBand} aria-labelledby="search-title">
          <div className={styles.marketTabs} aria-label="Market tabs">
            {(["domestic", "overseas"] as MarketScope[]).map((scope) => (
              <button
                className={scope === marketScope ? styles.marketTabActive : styles.marketTab}
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
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={t.searchPlaceholder}
            />
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
                <AlertCircle size={16} />
                <span>{dataError}</span>
              </div>
            ) : null}
            <div className={styles.stockList}>
              {filteredStocks.length ? (
                filteredStocks.map((stock) => (
                  <button
                    className={`${styles.stockRow} ${
                      stock.symbol === selectedStock.symbol ? styles.stockRowSelected : ""
                    }`}
                    key={stock.symbol}
                    type="button"
                    onClick={() => selectStock(stock.symbol)}
                  >
                    <span>
                      <strong>{stock.symbol}</strong>
                      <small>{stockName(stock, language)}</small>
                    </span>
                    <span className={stock.change >= 0 ? styles.positive : styles.negative}>
                      {stock.change >= 0 ? <TrendingUp size={15} /> : <TrendingDown size={15} />}
                      {stock.change > 0 ? "+" : ""}
                      {stock.change.toFixed(2)}%
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
                className={isWatched ? styles.watchButtonActive : styles.watchButton}
                type="button"
                onClick={() => toggleWatchlist(selectedStock.symbol)}
              >
                {isWatched ? <Star size={17} fill="currentColor" /> : <Plus size={17} />}
                {isWatched ? t.watching : t.addToWatchlist}
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
            </div>
            <div className={styles.sourceMeta}>
              <span>{selectedStock.source ?? "Sample data"}</span>
              <span>
                {t.updated} {formatFetchedAt(selectedStock.fetchedAt ?? latestFetchedAt, language)}
              </span>
              <span>Volume {formatCompactNumber(selectedStock.volume, language)}</span>
            </div>

            <div className={styles.chartControls}>
              <div className={styles.chartTypeTabs} aria-label={t.chartType}>
                {(["candle", "line"] as ChartType[]).map((type) => (
                  <button
                    key={type}
                    className={type === chartType ? styles.rangeActive : ""}
                    type="button"
                    onClick={() => setChartType(type)}
                  >
                    {type === "candle" ? <BarChart3 size={15} /> : <LineChart size={15} />}
                    {type === "candle" ? t.candle : t.line}
                  </button>
                ))}
              </div>
              <div className={styles.rangeTabs} aria-label={t.chartRange}>
                {ranges.map((rangeKey) => (
                  <button
                    key={rangeKey}
                    className={rangeKey === range ? styles.rangeActive : ""}
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
                    <stop offset="0%" stopColor="#a78bfa" stopOpacity="0.3" />
                    <stop offset="68%" stopColor="#8b5cf6" stopOpacity="0.1" />
                    <stop offset="100%" stopColor="#22c55e" stopOpacity="0" />
                  </linearGradient>
                </defs>
                {yAxisTicks.map((tick) => {
                  const y = yFor(tick, chartMin, chartMax, chartHeight, chartPadding);

                  return (
                    <g key={tick.toFixed(2)}>
                      <line
                        className={styles.gridLine}
                        x1={chartPadding}
                        x2={chartWidth - chartPadding}
                        y1={y}
                        y2={y}
                      />
                      <text className={styles.axisLabel} x={chartPadding} y={y - 6}>
                        {formatAxisPrice(tick, selectedStock.currency)}
                      </text>
                    </g>
                  );
                })}
                {xAxisIndexes.map((index) => {
                  const x = xFor(index, selectedPoints.length, chartWidth, chartPadding);

                  return (
                    <g key={`${range}-${selectedPoints[index].label}`}>
                      <line
                        className={styles.verticalGridLine}
                        x1={x}
                        x2={x}
                        y1={chartPadding}
                        y2={chartHeight - chartPadding}
                      />
                      <text
                        className={styles.axisLabel}
                        textAnchor="middle"
                        x={x}
                        y={chartHeight - 8}
                      >
                        {selectedPoints[index].label}
                      </text>
                    </g>
                  );
                })}
                {chartType === "line" ? (
                  <>
                    <path
                      className={styles.areaPath}
                      d={`${path} L ${chartWidth - chartPadding} ${chartHeight - chartPadding} L ${chartPadding} ${
                        chartHeight - chartPadding
                      } Z`}
                    />
                    <path className={styles.pricePath} d={path} />
                  </>
                ) : (
                  <g className={styles.candleLayer}>
                    {selectedCandles.map((candle, index) => {
                      const x = xFor(index, selectedCandles.length, chartWidth, chartPadding);
                      const openY = yFor(candle.open, chartMin, chartMax, chartHeight, chartPadding);
                      const closeY = yFor(candle.close, chartMin, chartMax, chartHeight, chartPadding);
                      const highY = yFor(candle.high, chartMin, chartMax, chartHeight, chartPadding);
                      const lowY = yFor(candle.low, chartMin, chartMax, chartHeight, chartPadding);
                      const isUp = candle.close >= candle.open;
                      const bodyTop = Math.min(openY, closeY);
                      const bodyHeight = Math.max(Math.abs(closeY - openY), 4);

                      return (
                        <g
                          className={isUp ? styles.candleUp : styles.candleDown}
                          key={`${range}-${index}`}
                        >
                          <line x1={x} x2={x} y1={highY} y2={lowY} />
                          <rect
                            x={x - candleWidth / 2}
                            y={bodyTop}
                            width={candleWidth}
                            height={bodyHeight}
                            rx="0.5"
                          />
                        </g>
                      );
                    })}
                  </g>
                )}
                <line
                  className={styles.activeLine}
                  x1={activeCoordinates.x}
                  x2={activeCoordinates.x}
                  y1={chartPadding}
                  y2={chartHeight - chartPadding}
                />
                <circle
                  className={styles.activeDot}
                  cx={activeCoordinates.x}
                  cy={activeCoordinates.y}
                  r="6"
                />
              </svg>
              <div
                className={styles.chartTooltip}
                style={{ left: `${(activeCoordinates.x / chartWidth) * 100}%` }}
              >
                <span>
                  {selectedPoint.label}
                </span>
                <strong>
                  {selectedStock.currency === "KRW"
                    ? `${selectedPointValue.toLocaleString("ko-KR")} KRW`
                    : `$${selectedPointValue.toFixed(2)}`}
                </strong>
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
                <strong>
                  {selectedStock.currency === "KRW"
                    ? rangeHigh.toLocaleString("ko-KR")
                    : rangeHigh.toFixed(2)}
                </strong>
              </div>
              <div>
                <span>{t.rangeLow}</span>
                <strong>
                  {selectedStock.currency === "KRW"
                    ? rangeLow.toLocaleString("ko-KR")
                    : rangeLow.toFixed(2)}
                </strong>
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
                <button
                  className={styles.watchRow}
                  key={stock.symbol}
                  type="button"
                  onClick={() => selectStock(stock.symbol)}
                >
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
            <div className={styles.notePanel}>
              <LineChart size={18} />
              <div>
                <strong>{t.automationPreview}</strong>
                <p>{t.automationText}</p>
                <div className={styles.automationSteps}>
                  <span>{t.dataBridge}</span>
                  <span>{t.manualReview}</span>
                </div>
              </div>
            </div>
          </aside>
        </section>

        <section className={styles.lowerGrid}>
          <div className={styles.signalPanel}>
            <div className={styles.panelHeader}>
              <div>
                <span>{t.portfolioSignalPanel}</span>
                <strong>{t.sentiment}</strong>
              </div>
              <a href="#top">{t.viewAll}</a>
            </div>
            <div className={styles.signalBody}>
              <div className={styles.scoreRing}>
                <span>68</span>
              </div>
              <div className={styles.signalTable}>
                <span>{t.topSignals}</span>
                {marketStocks.slice(0, 3).map((stock) => (
                  <div key={stock.symbol}>
                    <strong>{stock.symbol}</strong>
                    <span>{stock.strategy}</span>
                    <small>{signalLabel(stock.signal, language)}</small>
                  </div>
                ))}
              </div>
            </div>
          </div>
          <div className={styles.researchPanel}>
            <div className={styles.panelHeader}>
              <div>
                <span>{t.researchNotes}</span>
                <strong>{marketScope === "domestic" ? "KOSPI memo" : "NASDAQ memo"}</strong>
              </div>
            </div>
            <div className={styles.researchList}>
              {marketStocks.slice(0, 3).map((stock) => (
                <div key={stock.symbol}>
                  <span>{stock.signal}</span>
                  <strong>{stock.symbol} strategy note</strong>
                  <small>{stock.strategy}</small>
                </div>
              ))}
            </div>
          </div>
        </section>
      </section>
    </main>
  );
}
