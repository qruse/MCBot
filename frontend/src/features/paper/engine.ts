import type { Config, MarketSnapshot, Session, SessionEvent, Theme } from "./types";
import { allocate, mark, valuation } from "./accounting";
import { inspectRisk } from "./risk";
import { rankThemes, themeRollover } from "./strategy";
import { strategyIssue } from "./validation";

const STRATEGY_VERSION = "theme-top3-v1";

/** Transitional browser paper engine. No React, network, brokerage or persistence dependencies. */
export class PaperEngine {
  private state: Session;
  private decisions = new Set<string>();
  private commands = new Set<string>();
  private eventCounter = 0;
  private fillCounter = 0;

  constructor(config: Config, private themes: Theme[], id: string) {
    if (!Number.isFinite(config.capital) || config.capital < 1_000_000 || config.capital > 1_000_000_000_000
      || !["KR", "US"].includes(config.market)
      || config.stopPercent !== 2 || config.sidecarPercent !== 5) throw new Error("Invalid session configuration");
    this.state = {
      id, version: 0, evaluatedAt: 0, config: { ...config }, lifecycle: "idle", condition: "warming_up",
      reason: "Start a paper session to prepare the strategy.", baseline: null, cash: config.capital,
      positions: [], fills: [], events: [], samples: [], gaps: [], segment: 0,
      ready: 0, total: new Set(themes.filter(theme => theme.market === config.market).flatMap(theme => theme.symbols)).size,
      activeTheme: null, latest: null,
    };
  }

  view(): Session {
    return structuredClone(this.state);
  }

  private event(kind: SessionEvent["kind"], code: string, text: string, now: number, symbol?: string) {
    this.state.events.push({ id: ++this.eventCounter, timestamp: now, snapshotId: this.state.latest?.id ?? null,
      kind, code, text, symbol });
    this.state.events = this.state.events.slice(-200);
  }

  private gap(reason: string, now: number) {
    const previous = this.state.gaps.at(-1);
    if (previous?.end === null) {
      if (previous.reason === reason) return;
      previous.end = now;
    }
    this.state.segment++;
    this.state.gaps.push({ start: now, end: null, reason });
    this.state.gaps = this.state.gaps.slice(-200);
    this.event("data", "sampling_gap", reason, now);
  }

  private endGap(now: number) {
    const current = this.state.gaps.at(-1);
    if (current?.end === null) current.end = now;
  }

  private condition(now: number) {
    const s = this.state;
    s.evaluatedAt = now;
    const input = s.latest;
    const symbols = [...new Set(this.themes.filter(theme => theme.market === s.config.market).flatMap(theme => theme.symbols))];
    s.total = symbols.length;
    s.ready = input ? symbols.filter(symbol => !strategyIssue(symbol, input, now)).length : 0;
    if (!input) { s.condition = "warming_up"; s.reason = "Waiting for a market snapshot."; }
    else if (input.provider === "authentication_error") { s.condition = "authentication_error"; s.reason = "Provider authentication failed. Fix access before retrying."; }
    else if (input.provider === "cooldown") { s.condition = "provider_cooldown"; s.reason = "Provider is cooling down; new entries are blocked. Cached valid risk checks remain available."; }
    else if (!input.marketOpen) { s.condition = "market_closed"; s.reason = "Market session is closed. No simulated fills."; }
    else if (valuation(s.cash, s.positions, input, now, s.config) === null) { s.condition = "data_stale"; s.reason = "Held-price or FX data is invalid. Profit sampling is suspended; valid individual risk checks continue."; }
    else if (s.ready < s.total) { s.condition = "warming_up"; s.reason = `Strategy ready ${s.ready}/${s.total}. New entries wait; valid held-position risk checks continue.`; }
    else { s.condition = "ready"; s.reason = input.closingSoon ? "Closing window: entries blocked and valid holdings exited." : "Strategy inputs are ready. Waiting for the next unique market snapshot."; }
    if (s.lifecycle === "paused") s.reason = "User paused decisions, risk checks and profit sampling. Resume keeps the original baseline.";
    if (s.lifecycle === "halted") s.reason = "Portfolio sidecar halted this session. Review the risk event and acknowledge before creating a new session.";
  }

  command(action: "start" | "pause" | "resume", id: string, now: number) {
    if (this.commands.has(id)) return;
    this.commands.add(id);
    const s = this.state;
    if (action === "start" && s.lifecycle === "idle") {
      s.lifecycle = "preparing";
      this.event("command", "start", "Paper session requested; configuration and baseline belong to this session.", now);
    } else if (action === "pause" && (s.lifecycle === "running" || s.lifecycle === "preparing")) {
      s.lifecycle = "paused";
      this.gap("User pause: risk checks and samples stopped", now);
      this.event("command", "pause", "Paper session paused.", now);
    } else if (action === "resume" && s.lifecycle === "paused") {
      s.lifecycle = s.baseline === null ? "preparing" : "running";
      this.event("command", "resume", "Resumed with the original configuration and profit baseline.", now);
    }
    s.version++;
    this.condition(now);
    this.prepare(now);
  }

  private prepare(now: number) {
    const s = this.state;
    if (s.lifecycle !== "preparing" || s.condition !== "ready" || !s.latest) return;
    const equity = valuation(s.cash, s.positions, s.latest, now, s.config);
    if (equity === null) return;
    s.baseline = equity;
    s.lifecycle = "running";
    this.endGap(now);
    this.event("command", "prepared", "Preparation complete; initial liquidation-equity baseline recorded.", now);
    this.sample(now);
  }

  ingest(input: MarketSnapshot, now: number) {
    const s = this.state;
    if (!input.id || input.market !== s.config.market || !Number.isFinite(input.observedAt)
      || input.observedAt > now + 5_000 || input.observedAt <= 0) {
      this.event("data", "input_refused", "Snapshot identity, market or observation time is invalid; previous inputs retained.", now);
      s.version++;
      return;
    }
    const decisionId = `${s.id}:${STRATEGY_VERSION}:${input.id}`;
    // Repeated or out-of-order input must not restore older prices or re-enter after an exit.
    if ((s.latest && input.observedAt < s.latest.observedAt) || this.decisions.has(decisionId)) return;
    s.latest = structuredClone(input);
    this.condition(now);
    this.prepare(now);
    if (s.lifecycle !== "running") { s.version++; return; }
    this.decisions.add(decisionId);
    if (!input.marketOpen) { this.event("decision", "market_closed", s.reason, now); s.version++; return; }

    // Always run holding risk first. Candidate, provider and account-wide readiness are irrelevant here.
    const risk = inspectRisk(s.positions, input, now, s.config);
    risk.unavailable.forEach(item => this.event("risk", "risk_unavailable", `${item.symbol}: ${item.reason}. No fill; this holding's protection cannot be evaluated.`, now, item.symbol));
    if (!risk.sidecarAvailable) this.event("risk", "sidecar_unavailable", "Aggregate sidecar needs valid prices for every holding; valid individual stops still run.", now);
    risk.exits.forEach(exit => this.sell(exit.symbol, exit.reason, now));
    if (risk.sidecar) {
      this.sample(now);
      s.lifecycle = "halted";
      this.event("risk", "sidecar_halt", "5% holding-loss sidecar triggered. Explicit acknowledgement is required for a new session.", now);
      this.gap("Portfolio sidecar halt", now);
      this.condition(now);
      s.version++;
      return;
    }

    const themes = this.themes.filter(theme => theme.market === s.config.market);
    const active = themes.find(theme => theme.id === s.activeTheme);
    let exited = risk.exits.length > 0;
    if (active && s.positions.length && themeRollover(active, input, now)) {
      s.positions.slice().forEach(position => { if (this.sell(position.symbol, "Theme moving-average rollover", now)) exited = true; });
    }
    // An exit never re-enters on the same input. Complete candidate data is required for ranking.
    if (s.condition !== "ready") this.event("decision", "entry_blocked", s.reason, now);
    if (!exited && s.condition === "ready" && !input.closingSoon) {
      const winner = rankThemes(themes, input).find(value => value.eligible);
      if (!winner) this.event("decision", "no_uptrend", "Complete candidate set has no qualifying uptrend; no entry.", now);
      if (winner && s.positions.length && winner.theme.id !== s.activeTheme) {
        s.positions.slice().forEach(position => this.sell(position.symbol, "Rotation to the leading theme", now));
        exited = true;
      }
      if (winner && !exited && !s.positions.length) {
        const entries = allocate(winner.theme.symbols.slice(0, 3), s.cash, input, now, s.config);
        const cost = entries.reduce((sum, position) => sum + position.entryCost, 0);
        if (entries.length && cost <= s.cash + 0.000001) {
          s.cash = Math.max(0, s.cash - cost);
          s.positions = entries;
          s.activeTheme = winner.theme.id;
          entries.forEach(position => {
            s.fills.push({ id: `${s.id}:${++this.fillCounter}`, snapshotId: input.id, timestamp: now,
              symbol: position.symbol, side: "buy", shares: position.shares, priceKrw: position.entryPrice,
              fx: position.entryFx, gross: position.shares * position.entryPrice, fee: position.entryFee,
              reason: "Leading uptrend theme / balanced TOP3", netProfit: null });
            this.event("buy", "theme_entry", `Bought ${position.shares} ${position.symbol}: leading uptrend theme / balanced TOP3.`, now, position.symbol);
          });
        }
      }
    }
    this.condition(now);
    s.version++;
  }

  private sell(symbol: string, reason: string, now: number) {
    const s = this.state;
    const position = s.positions.find(item => item.symbol === symbol);
    if (!position || !s.latest) return false;
    const value = mark(position, s.latest, now, s.config);
    if (!value) { this.event("risk", "fill_refused", `${symbol}: invalid price or FX; ${reason} could not fill.`, now, symbol); return false; }
    s.cash += value.liquidation;
    s.positions = s.positions.filter(item => item.symbol !== symbol);
    s.fills.push({ id: `${s.id}:${++this.fillCounter}`, snapshotId: s.latest.id, timestamp: now, symbol,
      side: "sell", shares: position.shares, priceKrw: value.price,
      fx: s.latest.quotes[symbol]!.currency === "USD" ? s.latest.fx!.rate! : 1,
      gross: value.gross, fee: value.exitFee, reason, netProfit: value.profit });
    this.event(reason.includes("stop") || reason.includes("sidecar") ? "risk" : "sell", "position_exit", `Sold ${position.shares} ${symbol}: ${reason}.`, now, symbol);
    return true;
  }

  /** Sampling never evaluates strategy or requests fresh data. */
  sample(now: number) {
    const s = this.state;
    this.condition(now);
    if (s.lifecycle !== "running" || s.baseline === null || !s.latest) return;
    const equity = valuation(s.cash, s.positions, s.latest, now, s.config);
    if (equity === null || !s.latest.marketOpen || s.latest.provider !== "ready") {
      this.gap(equity === null ? "Held price or FX is stale / missing" : s.reason, now);
      s.version++;
      return;
    }
    this.endGap(now);
    const sources = s.positions.map(position => s.latest!.quotes[position.symbol]!.sourceTime);
    s.samples.push({ timestamp: now, snapshotId: s.latest.id, segment: s.segment, equity,
      cash: s.cash, holdings: s.positions.length, profit: equity - s.baseline,
      returnPercent: (equity - s.baseline) / s.baseline * 100,
      priceSourceTime: sources.length ? Math.min(...sources) : null,
      fxSourceTime: s.positions.some(position => s.latest!.quotes[position.symbol]!.currency === "USD") ? s.latest.fx!.validFrom : null });
    // This offline preview retains a rolling 1,000-sample window. Baseline/ledger are not truncated.
    s.samples = s.samples.slice(-1_000);
    s.version++;
  }
}
