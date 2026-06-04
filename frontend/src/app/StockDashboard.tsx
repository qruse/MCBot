"use client";

import {
  BarChart3,
  Bell,
  Briefcase,
  FileText,
  Home,
  LineChart,
  Plus,
  Search,
  Settings,
  Star,
  TrendingDown,
  TrendingUp,
  X,
  Zap,
} from "lucide-react";
import { useMemo, useState } from "react";

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
  sector: string;
  sectorKo: string;
  signal: "Buy" | "Watch" | "Hold";
  strategy: string;
  series: Record<RangeKey, number[]>;
};

type Candle = {
  open: number;
  high: number;
  low: number;
  close: number;
};

const ranges: RangeKey[] = ["LIVE", "1D", "1W", "1M", "1Y", "5Y", "ALL"];

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

function makeSeries(values: number[]): Record<RangeKey, number[]> {
  const first = values[0];
  const last = values[values.length - 1];
  const direction = last >= first ? 1 : -1;
  const spread = Math.max(Math.abs(last - first), Math.abs(last) * 0.012, 1);

  return {
    LIVE: values,
    "1D": values.map((value, index) => value + direction * spread * 0.08 * Math.sin(index)),
    "1W": values.map((value, index) => value - direction * spread * 0.22 + index * direction * spread * 0.055),
    "1M": values.map((value, index) => value - direction * spread * 0.72 + index * direction * spread * 0.15),
    "1Y": values.map((value, index) => value - direction * spread * 1.85 + index * direction * spread * 0.36),
    "5Y": values.map((value, index) => value - direction * spread * 4.6 + index * direction * spread * 0.82),
    ALL: values.map((value, index) => value - direction * spread * 7.4 + index * direction * spread * 1.22),
  };
}

const stocks: Stock[] = [
  {
    symbol: "AAPL",
    name: "Apple Inc.",
    localName: "Apple Inc.",
    market: "NASDAQ",
    region: "overseas",
    currency: "USD",
    price: 214.42,
    change: 1.84,
    sector: "Consumer Tech",
    sectorKo: "\uC18C\uBE44\uC790 \uAE30\uC220",
    signal: "Buy",
    strategy: "Trend Following",
    series: makeSeries([211.2, 211.8, 212.4, 212.1, 213.2, 213.8, 214.42]),
  },
  {
    symbol: "NVDA",
    name: "NVIDIA Corp.",
    localName: "NVIDIA Corp.",
    market: "NASDAQ",
    region: "overseas",
    currency: "USD",
    price: 142.65,
    change: 3.18,
    sector: "Semiconductors",
    sectorKo: "\uBC18\uB3C4\uCCB4",
    signal: "Buy",
    strategy: "Momentum",
    series: makeSeries([136.8, 138.1, 137.7, 140.2, 141.4, 141.9, 142.65]),
  },
  {
    symbol: "TSLA",
    name: "Tesla Inc.",
    localName: "Tesla Inc.",
    market: "NASDAQ",
    region: "overseas",
    currency: "USD",
    price: 184.21,
    change: -1.27,
    sector: "Automotive",
    sectorKo: "\uC790\uB3D9\uCC28",
    signal: "Watch",
    strategy: "Mean Reversion",
    series: makeSeries([187.4, 186.5, 185.8, 186.1, 184.9, 184.4, 184.21]),
  },
  {
    symbol: "MSFT",
    name: "Microsoft Corp.",
    localName: "Microsoft Corp.",
    market: "NASDAQ",
    region: "overseas",
    currency: "USD",
    price: 498.37,
    change: 0.72,
    sector: "Cloud Software",
    sectorKo: "\uD074\uB77C\uC6B0\uB4DC \uC18C\uD504\uD2B8\uC6E8\uC5B4",
    signal: "Hold",
    strategy: "Quality Growth",
    series: makeSeries([494.2, 495.8, 497.1, 496.6, 497.8, 498.1, 498.37]),
  },
  {
    symbol: "005930",
    name: "Samsung Electronics",
    localName: "\uC0BC\uC131\uC804\uC790",
    market: "KOSPI",
    region: "domestic",
    currency: "KRW",
    price: 73500,
    change: 0.55,
    sector: "Semiconductors",
    sectorKo: "\uBC18\uB3C4\uCCB4",
    signal: "Watch",
    strategy: "Cycle Recovery",
    series: makeSeries([72700, 72900, 73100, 73000, 73400, 73300, 73500]),
  },
  {
    symbol: "000660",
    name: "SK Hynix",
    localName: "SK\uD558\uC774\uB2C9\uC2A4",
    market: "KOSPI",
    region: "domestic",
    currency: "KRW",
    price: 198700,
    change: 2.42,
    sector: "Memory Chips",
    sectorKo: "\uBA54\uBAA8\uB9AC \uBC18\uB3C4\uCCB4",
    signal: "Buy",
    strategy: "Momentum",
    series: makeSeries([193500, 194800, 196200, 195900, 197100, 198200, 198700]),
  },
  {
    symbol: "035420",
    name: "NAVER",
    localName: "\uB124\uC774\uBC84",
    market: "KOSPI",
    region: "domestic",
    currency: "KRW",
    price: 184500,
    change: -0.88,
    sector: "Internet Platform",
    sectorKo: "\uC778\uD130\uB137 \uD50C\uB7AB\uD3FC",
    signal: "Hold",
    strategy: "Range Breakout",
    series: makeSeries([186000, 185700, 185100, 184200, 184900, 184100, 184500]),
  },
];

const initialWatchlist = ["AAPL", "NVDA", "005930", "000660"];

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

function buildPath(values: number[], width: number, height: number, padding: number) {
  const min = Math.min(...values);
  const max = Math.max(...values);
  const spread = max - min || 1;

  return values
    .map((value, index) => {
      const x = padding + (index / (values.length - 1)) * (width - padding * 2);
      const y = padding + ((max - value) / spread) * (height - padding * 2);

      return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
}

function pointFor(values: number[], index: number, width: number, height: number, padding: number) {
  const min = Math.min(...values);
  const max = Math.max(...values);
  const spread = max - min || 1;
  const x = padding + (index / (values.length - 1)) * (width - padding * 2);
  const y = padding + ((max - values[index]) / spread) * (height - padding * 2);

  return { x, y };
}

function buildCandles(values: number[]): Candle[] {
  return values.map((close, index) => {
    const previous = values[Math.max(index - 1, 0)];
    const open = index === 0 ? previous * 0.997 : previous;
    const bodySpread = Math.abs(close - open);
    const wickSpread = Math.max(Math.abs(close) * 0.004, bodySpread * 0.75, 1);
    const high = Math.max(open, close) + wickSpread * (0.75 + (index % 3) * 0.16);
    const low = Math.min(open, close) - wickSpread * (0.72 + (index % 2) * 0.18);

    return { open, high, low, close };
  });
}

function yFor(value: number, min: number, max: number, height: number, padding: number) {
  const spread = max - min || 1;

  return padding + ((max - value) / spread) * (height - padding * 2);
}

export default function StockDashboard() {
  const [query, setQuery] = useState("");
  const [marketScope, setMarketScope] = useState<MarketScope>("overseas");
  const [language, setLanguage] = useState<Language>("ko");
  const [selectedSymbol, setSelectedSymbol] = useState("AAPL");
  const [watchlist, setWatchlist] = useState(initialWatchlist);
  const [range, setRange] = useState<RangeKey>("LIVE");
  const [chartType, setChartType] = useState<ChartType>("candle");
  const [activePoint, setActivePoint] = useState<number | null>(null);

  const t = copy[language];
  const marketStocks = useMemo(
    () => stocks.filter((stock) => stock.region === marketScope),
    [marketScope],
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

  const selectedStock =
    stocks.find((stock) => stock.symbol === selectedSymbol && stock.region === marketScope) ??
    marketStocks[0];
  const selectedValues = selectedStock.series[range];
  const selectedCandles = buildCandles(selectedValues);
  const selectedIndex = activePoint ?? selectedValues.length - 1;
  const selectedPointValue = selectedValues[selectedIndex];
  const chartWidth = 820;
  const chartHeight = 310;
  const chartPadding = 28;
  const candleExtremes = selectedCandles.flatMap((candle) => [candle.high, candle.low]);
  const chartMin = Math.min(...selectedValues, ...candleExtremes);
  const chartMax = Math.max(...selectedValues, ...candleExtremes);
  const path = buildPath(selectedValues, chartWidth, chartHeight, chartPadding);
  const activeCoordinates = pointFor(
    selectedValues,
    selectedIndex,
    chartWidth,
    chartHeight,
    chartPadding,
  );
  const watchedStocks = watchlist
    .map((symbol) => stocks.find((stock) => stock.symbol === symbol))
    .filter((stock): stock is Stock => Boolean(stock))
    .filter((stock) => stock.region === marketScope);
  const isWatched = watchlist.includes(selectedStock.symbol);
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
          <strong>MCBot</strong>
          <span>{t.appName}</span>
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
        </div>
      </aside>

      <section className={styles.mainStage}>
        <header className={styles.topbar}>
          <div>
            <span className={styles.productName}>MCBot</span>
            <h1>{t.appName}</h1>
            <p>{t.appSubtitle}</p>
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
            <small>{t.dataMode}</small>
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
                <span>{selectedStock.market}</span>
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
                    <stop offset="0%" stopColor="#38bdf8" stopOpacity="0.28" />
                    <stop offset="68%" stopColor="#22c55e" stopOpacity="0.1" />
                    <stop offset="100%" stopColor="#22c55e" stopOpacity="0" />
                  </linearGradient>
                </defs>
                {[0, 1, 2, 3].map((line) => (
                  <line
                    key={line}
                    className={styles.gridLine}
                    x1="0"
                    x2={chartWidth}
                    y1={chartPadding + line * 82}
                    y2={chartPadding + line * 82}
                  />
                ))}
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
                      const x =
                        chartPadding +
                        (index / (selectedCandles.length - 1)) * (chartWidth - chartPadding * 2);
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
                            x={x - 13}
                            y={bodyTop}
                            width="26"
                            height={bodyHeight}
                            rx="3"
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
                  {t.point} {selectedIndex + 1}
                </span>
                <strong>
                  {selectedStock.currency === "KRW"
                    ? `${selectedPointValue.toLocaleString("ko-KR")} KRW`
                    : `$${selectedPointValue.toFixed(2)}`}
                </strong>
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
