"""One owner commits paper accounting, proposal receipts and research provenance."""

import asyncio
import hashlib
import json
import os
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from app import toss
from app.paper import domain
from app.paper.contracts import AdaptivePortfolioPlan, Command, Proposal, Settings, standing_groups
from app.paper.market import Collector, GlobalCollector, demo_snapshot
from app.paper.storage import Store, encode
from app.paper.strategies.registry import Registry, reference
from app.paper.strategies.runtime import StrategyError


def now_ms():
    return int(time.time() * 1000)


def identity():
    return uuid.uuid4().hex


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(encode(value), encoding="utf-8")
    os.replace(temporary, path)


class Conflict(ValueError):
    pass


class PaperService:
    def __init__(self, database, exchange):
        self.store = Store(database)
        self.strategies = Registry(self.store)
        self.exchange = Path(exchange)
        for name in ("exports", "inbox", "receipts", "scratch"):
            (self.exchange / name).mkdir(parents=True, exist_ok=True)
        self.lock = asyncio.Lock()
        self.collector = None
        self.collector_id = None
        self.tasks = []
        self.last_export = 0
        self.last_error = None
        with self.store.transaction():
            bundle = self.store.current()
            if bundle is None:
                bundle = self.new_bundle(Settings())
            for key in ("session", "benchmark"):
                s = bundle[key]
                s["isBenchmark"] = key == "benchmark"
                if key == "session" and "standingGroups" not in s:
                    s["standingGroups"] = standing_groups(s["config"]["market"])
                    s["pending"] = None
                    domain.event(s, "standing_candidates_added", now_ms(), "command")
                if s["lifecycle"] in ("preparing", "running"):
                    s["lifecycle"] = "paused"
                    s["pending"] = None
                    s["version"] += 1
                    domain.gap(s, "restart_paused", now_ms())
                    domain.event(s, "restart_paused", now_ms(), "command")
            self.store.save(bundle)
        self.export(now_ms())

    @staticmethod
    def new_bundle(settings):
        session = domain.create(settings, identity())
        reference_settings = settings.model_copy(update={"market": "KR"}) if (
            settings.market == "GLOBAL") else settings
        benchmark = domain.create(reference_settings, f"{session['id']}-reference")
        benchmark["mode"] = "observer"
        benchmark["isBenchmark"] = True
        benchmark["standingGroups"] = []
        return {"session": session, "benchmark": benchmark}

    def view(self, session_id=None):
        if session_id:
            row = self.store.db.execute(
                "SELECT payload FROM sessions WHERE id=?", (session_id,)
            ).fetchone()
            if not row:
                raise Conflict("session_not_found")
            bundle = json.loads(row[0])
        else:
            bundle = self.store.current()
        s = bundle["session"]
        domain.assess(s, now_ms())
        from app.paper.portfolio import status

        s["portfolioStatus"] = status(s, now_ms())
        s["samples"] = self.store.samples(s["id"])
        s["events"] = s["events"][-200:]
        s["fills"] = s["fills"][-200:]
        s["gaps"] = s["gaps"][-200:]
        reference = bundle["benchmark"]["samples"][-1:]
        last = s["samples"][-1:]
        paired = bool(s["config"]["market"] != "GLOBAL" and last and reference
                      and last[0]["timestamp"] == reference[0]["timestamp"])
        receipts = [
            json.loads(row[0])
            for row in self.store.db.execute(
                "SELECT receipt FROM proposals ORDER BY rowid DESC LIMIT 20"
            )
        ]
        runs = [
            dict(row)
            for row in self.store.db.execute(
                "SELECT * FROM runs WHERE session_id=? ORDER BY started DESC LIMIT 12", (s["id"],)
            )
        ]
        experiments = []
        for row in self.store.db.execute("SELECT * FROM experiments ORDER BY registered DESC"):
            e = json.loads(row["payload"])
            e.update(
                status=row["status"], registered_at=row["registered"], session_id=row["session_id"]
            )
            # Independent forward sessions, not sample count or winning-trade narratives.
            evidence = []
            for stored in self.store.db.execute("SELECT payload FROM sessions"):
                candidate = json.loads(stored[0])
                a, b = candidate["session"], candidate["benchmark"]
                if a["source"] == "demo" or a["mode"] != "adaptive":
                    continue
                if a["lifecycle"] not in ("paused", "halted") or a["positions"]:
                    continue
                fills = [
                    f
                    for f in a["fills"]
                    if f["side"] == "sell" and f["timestamp"] > row["registered"]
                ]
                if not fills or not a["samples"] or not b["samples"]:
                    continue
                # Evidence belongs only to plans that preregistered this experiment.
                linked = self.store.db.execute(
                    "SELECT payload FROM proposals WHERE id IN ("
                    + ",".join("?" for _ in fills)
                    + ")",
                    [f["proposalId"] for f in fills],
                ).fetchall()
                if not any(
                    (json.loads(p[0]).get("experiment") or {}).get("experiment_id")
                    == e["experiment_id"]
                    for p in linked
                ):
                    continue
                av, bv = a["samples"][-1], b["samples"][-1]
                if av["timestamp"] == bv["timestamp"]:
                    evidence.append(
                        {
                            "session_id": a["id"],
                            "timestamp": av["timestamp"],
                            "market": a["config"]["market"],
                            "trading_day": datetime.fromtimestamp(
                                av["timestamp"] / 1000,
                                ZoneInfo(
                                    "Asia/Seoul"
                                    if a["config"]["market"] == "KR"
                                    else "America/New_York"
                                ),
                            )
                            .date()
                            .isoformat(),
                            "difference": str(domain.D(av["profit"]) - domain.D(bv["profit"])),
                        }
                    )
            e["outcomes"] = evidence
            days = {(item["market"], item["trading_day"]) for item in evidence}
            e["independent_sessions"] = len(days)
            e["promotion_eligible"] = False  # Costs/forward gates still require review.
            experiments.append(e)
        archives = [
            dict(row)
            for row in self.store.db.execute(
                "SELECT id,active FROM sessions ORDER BY rowid DESC LIMIT 20"
            )
        ]
        return {
            "session": s,
            "research": {
                "cadenceMinutes": 60,
                "validityMinutes": 75,
                "runtimeMinutes": 10,
                "lastRun": runs[0] if runs else None,
                "runs": runs,
                "receipts": receipts,
                "experiments": experiments,
                "trialCount": len(experiments),
                "benchmark": reference[0] if reference else None,
                "difference": str(domain.D(last[0]["profit"]) - domain.D(reference[0]["profit"]))
                if paired
                else None,
                "paired": paired,
                "archives": archives,
                "nextReviewDue": (now_ms() // 3600000 + 1) * 3600000,
                "exchange": "runtime/agent_exchange",
                "engineError": self.last_error,
                "providerStatus": (
                    toss.status() if s["source"] == "toss" and not session_id else None
                ),
                "admitted": [item["ref"] for item in self.strategies.catalog()],
                "strategies": self.strategies.catalog(),
                "strategyFeedback": self.strategies.feedback(),
                "strategyEvaluations": self.strategies.evaluations(),
            },
        }

    def command(self, cmd: Command, now):
        payload = encode(cmd.model_dump(mode="json"))
        with self.store.transaction() as db:
            previous = db.execute(
                "SELECT request,receipt FROM commands WHERE id=?", (cmd.command_id,)
            ).fetchone()
            if previous:
                if previous["request"] != payload:
                    raise Conflict("command_id_reused")
                return json.loads(previous["receipt"])
            bundle = self.store.current()
            s = bundle["session"]
            if cmd.session_id != s["id"] or cmd.expected_version != s["version"]:
                raise Conflict("version_conflict")
            active = s["lifecycle"] in ("preparing", "running")
            if cmd.action in ("new", "use_toss"):
                if active:
                    raise Conflict("stop_before_new_session")
                if cmd.action == "use_toss":
                    if s["source"] != "demo" or not cmd.settings or cmd.settings.source != "toss":
                        raise Conflict("demo_to_toss_only")
                    # Preserve the synthetic book exactly; never transfer its prices or holdings.
                    for state in (s, bundle["benchmark"]):
                        state["pending"] = None
                        state["version"] += 1
                        domain.event(state, "demo_archived_for_toss", now, "command")
                    self.store.save(bundle)
                elif s["positions"]:
                    raise Conflict("positions_require_exit_before_new_session")
                db.execute("UPDATE sessions SET active=0 WHERE active=1")
                bundle = self.new_bundle(cmd.settings or Settings())
            elif cmd.action in ("enable_global", "enable_global_preserving"):
                from app.paper.global_account import enable
                try:
                    enable(s, db, now, preserve_holdings=cmd.action == "enable_global_preserving")
                except ValueError as exc:
                    raise Conflict(str(exc)) from exc
                s["version"] += 1
                domain.event(s, cmd.action, now, "command")
            else:
                for state in (s, bundle["benchmark"]):
                    if state is not s and (
                        cmd.action == "pause"
                        and state["lifecycle"] in ("paused", "halted")
                        or cmd.action == "resume"
                        and state["lifecycle"] in ("running", "preparing", "halted")
                        or cmd.action == "enable_continuous"
                        and state["lifecycle"] == "halted"
                    ):
                        # A stopped reference lane cannot block primary account control.
                        continue
                    if cmd.action == "enable_continuous" and state["lifecycle"] in (
                        "idle",
                        "preparing",
                        "running",
                        "paused",
                    ):
                        state["continuousPaper"] = True
                        state["leaseUntil"] = now + 86400000
                    elif cmd.action == "start" and state["lifecycle"] == "idle":
                        state["lifecycle"] = "preparing"
                        state["leaseUntil"] = now + 86400000
                    elif cmd.action == "resume" and state["lifecycle"] == "paused":
                        state["lifecycle"] = "running" if state["baseline"] else "preparing"
                        state["leaseUntil"] = now + 86400000
                        state["lastDecision"] = None
                    elif cmd.action == "pause" and state["lifecycle"] in ("running", "preparing"):
                        domain.sample(state, now, force=True)
                        state["lifecycle"] = "paused"
                        state["pending"] = None
                        domain.gap(state, "user_pause", now)
                    elif cmd.action in ("pause_entries", "resume_entries") and active:
                        if state is s:
                            state["entriesPaused"] = cmd.action == "pause_entries"
                            state["pending"] = None
                    else:
                        raise Conflict("invalid_lifecycle")
                    state["version"] += 1
                    domain.event(state, cmd.action, now, "command")
            self.store.save(bundle)
            receipt = {
                "command_id": cmd.command_id,
                "session_id": bundle["session"]["id"],
                "version": bundle["session"]["version"],
                "status": "accepted",
            }
            db.execute(
                "INSERT INTO commands VALUES(?,?,?)", (cmd.command_id, payload, encode(receipt))
            )
        self.export(now)
        return receipt

    def claim(self, run_id, now, manual_reason=None, session_id=None, expected_policy_version=None):
        manual = manual_reason is not None
        request = encode(
            {
                "run_id": run_id,
                "reason": manual_reason,
                "session_id": session_id,
                "policy_version": expected_policy_version,
            }
        )
        with self.store.transaction() as db:
            bundle = self.store.current()
            s = bundle["session"]
            if manual:
                prior = db.execute(
                    "SELECT request,receipt FROM commands WHERE id=?", (f"research:{run_id}",)
                ).fetchone()
                if prior:
                    if prior["request"] != request:
                        raise Conflict("run_id_reused")
                    return json.loads(prior["receipt"])
                if session_id != s["id"] or expected_policy_version != s["policyVersion"]:
                    raise Conflict("policy_version_conflict")
                if not manual_reason.strip() or s["lifecycle"] not in ("preparing", "running"):
                    raise Conflict("manual_review_requires_active_session")
            elif session_id is not None or expected_policy_version is not None:
                raise Conflict("manual_reason_required")
            existing = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            if existing:
                if manual or existing["slot"] is None or existing["session_id"] != s["id"]:
                    raise Conflict("run_id_reused")
                return dict(existing)
            overlap = db.execute(
                "SELECT id FROM runs WHERE session_id=? AND slot=?", (s["id"], now // 3600000)
            ).fetchone()
            if overlap and not manual:
                raise Conflict("hourly_slot_already_claimed")
            if db.execute(
                "SELECT id FROM runs WHERE session_id=? AND completed IS NULL AND deadline>=?",
                (s["id"], now),
            ).fetchone():
                raise Conflict("research_run_in_progress")
            # NULL is an explicit owner-triggered review, outside scheduled hourly slots.
            # Existing UNIQUE(session_id,slot) still enforces the hourly reservation.
            db.execute(
                "INSERT INTO runs VALUES(?,?,?,?,?,NULL)",
                (run_id, s["id"], None if manual else now // 3600000, now, now + 600000),
            )
            receipt = {"id": run_id, "session_id": s["id"], "deadline": now + 600000}
            if manual:
                db.execute(
                    "INSERT INTO commands VALUES(?,?,?)",
                    (f"research:{run_id}", request, encode(receipt)),
                )
                domain.event(s, "manual_research_requested", now, "command")
                s["events"][-1].update(run_id=run_id, reason=manual_reason)
                self.store.save(bundle)
        self.export(now)
        return receipt

    def validate_proposal(self, proposal, now, s, db):
        try:
            module = self.strategies.get(reference(proposal.playbook_id, proposal.strategy_version))
        except StrategyError:
            return "strategy_not_registered"
        if proposal.session_id != s["id"] or proposal.market != s["config"]["market"]:
            return "wrong_session"
        if proposal.base_policy_version != s["policyVersion"]:
            return "policy_version_conflict"
        run = db.execute("SELECT * FROM runs WHERE id=?", (proposal.run_id,)).fetchone()
        if (
            not run
            or run["session_id"] != s["id"]
            or run["completed"]
            or not run["started"] <= now <= run["deadline"]
        ):
            return "run_missing_or_expired"
        export = db.execute(
            "SELECT payload FROM exports WHERE id=?", (proposal.snapshot_id,)
        ).fetchone()
        if not export:
            return "unknown_snapshot"
        context = json.loads(export[0])
        if context["session"]["id"] != s["id"]:
            return "wrong_snapshot_session"
        if not context["as_of"] <= proposal.as_of <= now:
            return "invalid_evidence_cutoff"
        if not proposal.as_of <= proposal.valid_from <= now < proposal.expires_at:
            return "invalid_validity"
        if proposal.expires_at - proposal.as_of > 4500000:
            return "validity_exceeds_75_minutes"
        if now - context["as_of"] > 600000:
            return "stale_context"
        if len(set(proposal.allowed_symbols)) != len(proposal.allowed_symbols):
            return "duplicate_symbols"
        if len({e.evidence_id for e in proposal.evidence}) != len(proposal.evidence):
            return "duplicate_evidence_ids"
        global_mode = proposal.market == "GLOBAL"
        pattern = (r"(?:KR:[A-Z0-9]{6}|US:[A-Z][A-Z0-9.\-]{0,19})" if global_mode
                   else r"[A-Z0-9]{6}" if proposal.market == "KR"
                   else r"[A-Z][A-Z0-9.\-]{0,19}")
        if any(not re.fullmatch(pattern, symbol) for symbol in proposal.allowed_symbols):
            return "unsupported_symbols"
        groups = proposal.candidate_groups
        def instrument(item):
            return f"{item.market}:{item.symbol}" if global_mode else item.symbol
        selected = [instrument(item) for group in groups for item in group.candidates]
        # New submissions follow the owner cap even through the legacy v4 adapter.
        # Previously recorded policies and ledgers are never rewritten.
        if len(selected) > 5:
            return "general_candidate_budget_exceeded"
        if len(set(group.group_id for group in groups)) != len(groups):
            return "duplicate_candidate_groups"
        if len(set(selected)) != len(selected):
            return "duplicate_symbols"
        if selected != proposal.allowed_symbols:
            return "candidate_symbols_mismatch"
        reserved = ({instrument(item) for group in proposal.inverse_groups
                     for item in group.candidates}
                    if global_mode else set(domain.standing_symbols(s)))
        if global_mode:
            from app.paper.investment_universe import INDEX_INVERSES, inverse_issue
            if any(instrument(item) in INDEX_INVERSES
                   for group in groups for item in group.candidates):
                return "general_etf_excluded"
            for key in selected:
                security = (s.get("latest") or {}).get("securities", {}).get(key)
                if security and security.get("securityType") not in ("STOCK", "FOREIGN_STOCK"):
                    return "general_etf_excluded"
            for key in reserved:
                security = (s.get("latest") or {}).get("securities", {}).get(key)
                if security and inverse_issue(key, security):
                    return "index_inverse_ineligible"
        retirements = []
        if proposal.portfolio:
            weights = proposal.portfolio.target_weights
            adaptive = isinstance(proposal.portfolio, AdaptivePortfolioPlan)
            if adaptive:
                retirements = proposal.portfolio.retirements
                from app.paper.global_account import lot_key
                retired = {instrument(item) for item in retirements}
                held = {lot_key(s, p) if global_mode else p["symbol"] for p in s["positions"]}
                if (
                    len(retired) != len(retirements)
                    or retired != held - set(selected) - reserved
                    or any(weights.get(symbol) != 0 for symbol in retired)
                    or any(weights.get(symbol, 0) <= 0 for symbol in selected)
                ):
                    return "invalid_retirements"
            else:
                retired = set()
            if (
                module["protocol_version"] != (5 if global_mode else 4 if adaptive else 3)
                or set(weights) != set(selected) | reserved | retired | {"CASH"}
                or (1 - weights["CASH"]) * 100 > proposal.max_exposure_percent
            ):
                return "invalid_portfolio_scope"
        elif module["protocol_version"] >= 3:
            return "portfolio_plan_required"
        if any(
            group.group_id in {g["group_id"] for g in s.get("standingGroups", [])}
            for group in groups
        ):
            return "reserved_candidate_group"
        if set(selected) & reserved:
            return "standing_candidate_duplicate"
        if proposal.playbook_id != "cash-v1" and not selected and not reserved:
            return "candidates_required"
        if not set(proposal.entry_blocks) <= set(proposal.allowed_symbols) | reserved:
            return "invalid_entry_blocks"
        for evidence in proposal.evidence:
            if not 0 < evidence.published_at <= evidence.retrieved_at <= proposal.as_of:
                return "future_evidence"
            host = evidence.source_url.host or ""
            if host in ("localhost", "127.0.0.1", "::1") or evidence.source_url.scheme != "https":
                return "invalid_source_url"
            existing = db.execute(
                "SELECT payload FROM proposals WHERE "
                "json_extract(receipt,'$.status') IN ('accepted','observed')"
            ).fetchall()
            for row in existing:
                for prior in json.loads(row[0]).get("evidence", []):
                    if prior[
                        "evidence_id"
                    ] == evidence.evidence_id and prior != evidence.model_dump(mode="json"):
                        return "evidence_id_reused"
        if proposal.playbook_id != "cash-v1" and not proposal.evidence:
            return "evidence_required"
        evidence_ids = {item.evidence_id for item in proposal.evidence}
        if global_mode:
            evidence_map = {e.evidence_id: str(e.source_url) for e in proposal.evidence}
            for group in proposal.inverse_groups:
                if group.group_id in {g.group_id for g in groups}:
                    return "duplicate_candidate_groups"
                for item in group.candidates:
                    url = INDEX_INVERSES[instrument(item)]["source_url"]
                    if not set(item.evidence_ids) <= evidence_ids or url not in {
                        evidence_map[e] for e in item.evidence_ids if e in evidence_map
                    }:
                        return "index_inverse_evidence_required"
        if any(not set(item.evidence_ids) <= evidence_ids for item in retirements):
            return "invalid_retirement_evidence"
        if any(
            not set(item.evidence_ids) <= evidence_ids
            for group in groups
            for item in group.candidates
        ):
            return "candidate_evidence_missing"
        if proposal.experiment:
            ex = proposal.experiment
            if ex.review_after <= now:
                return "experiment_must_be_preregistered"
            existing = db.execute(
                "SELECT payload FROM experiments WHERE id=?", (ex.experiment_id,)
            ).fetchone()
            if existing and json.loads(existing[0]) != ex.model_dump(mode="json"):
                return "experiment_id_reused"
        if s["lifecycle"] not in ("preparing", "running"):
            return "session_inactive"
        if not s["latest"] or not s["latest"]["marketOpen"]:
            return "market_closed"
        if proposal.expires_at > min(s["leaseUntil"], s["latest"]["marketClose"]):
            return "beyond_session_close"
        return None

    def submit(self, value, proposal_id, now):
        digest = hashlib.sha256(encode(value).encode()).hexdigest()
        with self.store.transaction() as db:
            existing = db.execute(
                "SELECT digest,receipt FROM proposals WHERE id=?", (proposal_id,)
            ).fetchone()
            if existing:
                if existing["digest"] != digest:
                    return {
                        "proposal_id": proposal_id,
                        "status": "rejected",
                        "reason": "proposal_id_reused",
                        "timestamp": now,
                    }
                return json.loads(existing["receipt"])
            bundle = self.store.current()
            s = bundle["session"]
            proposal = None
            try:
                proposal = Proposal.model_validate(value)
                reason = (
                    "proposal_filename_mismatch"
                    if proposal.proposal_id != proposal_id
                    else self.validate_proposal(proposal, now, s, db)
                )
            except (ValidationError, ValueError, TypeError):
                reason = "invalid_schema"
            status = "rejected" if reason else "observed" if s["mode"] == "observer" else "accepted"
            if not reason:
                # Observation may prepare a proposed universe but never activates a trading plan.
                s["candidateGroups"] = [
                    group.model_dump(mode="json") for group in proposal.candidate_groups
                ]
                if proposal.market == "GLOBAL":
                    from app.paper.investment_universe import inverse_groups
                    s["standingGroups"] = inverse_groups(proposal.inverse_groups)
                s["candidateProposalId"] = proposal.proposal_id
                s["candidateExpiresAt"] = proposal.expires_at
                if proposal.experiment:
                    ex = proposal.experiment
                    db.execute(
                        "INSERT OR IGNORE INTO experiments(id,session_id,registered,payload) "
                        "VALUES(?,?,?,?)",
                        (ex.experiment_id, s["id"], now, encode(ex.model_dump(mode="json"))),
                    )
                if status == "accepted":
                    s["policy"] = proposal.model_dump(mode="json")
                    module = self.strategies.get(
                        reference(proposal.playbook_id, proposal.strategy_version)
                    )
                    s["policy"]["strategy_digest"] = module["digest"]
                    s["policy"]["strategy_name"] = module["name"]
                    s["policyVersion"] += 1
                    s["pending"] = None
                    domain.event(s, "policy_accepted", now)
                else:
                    domain.event(s, "policy_observed", now)
            elif proposal and proposal.session_id == s["id"]:
                domain.event(s, "policy_rejected", now)
            if proposal:
                db.execute(
                    "UPDATE runs SET completed=? WHERE id=? AND completed IS NULL",
                    (now, proposal.run_id),
                )
            receipt = {
                "proposal_id": proposal_id,
                "session_id": s["id"],
                "source": s["source"],
                "status": status,
                "reason": reason or ("observer_only" if status == "observed" else "validated"),
                "timestamp": now,
                "policy_version": s["policyVersion"],
                "playbook_id": proposal.playbook_id if proposal else None,
                "strategy_ref": reference(proposal.playbook_id, proposal.strategy_version)
                if proposal
                else None,
                "rationale": proposal.rationale if proposal else "Invalid proposal",
                "expires_at": proposal.expires_at if proposal else None,
                "candidate_groups": [
                    group.model_dump(mode="json") for group in proposal.candidate_groups
                ]
                if proposal
                else [],
                "candidate_gate": "pending_provider_validation"
                if not reason and (proposal.allowed_symbols or s.get("standingGroups"))
                else "not_requested",
                "standing_groups": s.get("standingGroups", []),
                "evidence": [e.model_dump(mode="json") for e in proposal.evidence]
                if proposal
                else [],
            }
            # Invalid content is kept as data, never evaluated as code.
            db.execute(
                "INSERT INTO proposals VALUES(?,?,?,?)",
                (proposal_id, digest, encode(value), encode(receipt)),
            )
            self.store.save(bundle)
        return receipt

    def rollback_strategy(self, cmd, now):
        payload = encode({"action": "rollback_strategy", **cmd.model_dump(mode="json")})
        with self.store.transaction() as db:
            previous = db.execute(
                "SELECT request,receipt FROM commands WHERE id=?", (cmd.command_id,)
            ).fetchone()
            if previous:
                if previous["request"] != payload:
                    raise Conflict("command_id_reused")
                return json.loads(previous["receipt"])
            bundle = self.store.current()
            s = bundle["session"]
            if s["id"] != cmd.session_id or s["policyVersion"] != cmd.expected_policy_version:
                raise Conflict("policy_version_conflict")
            if not s["policy"] or s["mode"] != "adaptive":
                raise Conflict("no_active_adaptive_policy")
            current = domain.policy_ref(s["policy"])
            parent = self.strategies.get(current)["parent_ref"]
            visited = set()
            while parent and parent != cmd.target_ref and parent not in visited:
                visited.add(parent)
                parent = self.strategies.get(parent)["parent_ref"]
            if parent != cmd.target_ref:
                raise Conflict("rollback_requires_ancestor")
            target = self.strategies.get(cmd.target_ref)
            if s["config"]["market"] == "GLOBAL" and target["protocol_version"] != 5:
                raise Conflict("global_protocol_required")
            s["policy"].update(
                playbook_id=target["strategy_id"],
                strategy_version=target["version"],
                strategy_digest=target["digest"],
                strategy_name=target["name"],
                rationale=cmd.reason,
                rolled_back_from=current,
            )
            s["policyVersion"] += 1
            s["pending"] = None
            s["strategyError"] = None
            domain.event(s, "strategy_rollback", now, "command")
            s["events"][-1].update(fromRef=current, strategyRef=cmd.target_ref, reason=cmd.reason)
            receipt = {
                "command_id": cmd.command_id,
                "status": "accepted",
                "from_ref": current,
                "strategy_ref": cmd.target_ref,
                "policy_version": s["policyVersion"],
                "reason": cmd.reason,
                "timestamp": now,
            }
            self.store.save(bundle)
            db.execute(
                "INSERT INTO commands VALUES(?,?,?)", (cmd.command_id, payload, encode(receipt))
            )
        self.export(now)
        return receipt

    def replay_inputs(self, strategy_ref, session_id):
        self.strategies.get(strategy_ref)
        row = self.store.db.execute(
            "SELECT payload FROM sessions WHERE id=?", (session_id,)
        ).fetchone()
        if not row:
            raise Conflict("session_not_found")
        state = json.loads(row[0])["session"]
        inputs = [
            json.loads(r[0])
            for r in self.store.db.execute(
                "SELECT DISTINCT o.payload FROM observations o JOIN samples s "
                "ON json_extract(s.payload,'$.snapshotId')=o.id WHERE s.session_id=? "
                "ORDER BY json_extract(o.payload,'$.observedAt') LIMIT 80",
                (session_id,),
            )
        ]
        modules = {
            item["ref"]: self.strategies.get(item["ref"]) for item in self.strategies.catalog()
        }
        return state, inputs, modules

    def inbox(self, now):
        for path in sorted((self.exchange / "inbox").glob("*.json"))[:20]:
            if path.is_symlink() or not path.is_file():
                continue
            try:
                if path.stat().st_size > 65536:
                    value = {"invalid": "size_limit"}
                else:
                    value = json.loads(path.read_text(encoding="utf-8-sig"))
                    if not isinstance(value, dict):
                        value = {"invalid": "object_required"}
                receipt = self.submit(value, path.stem, now)
            except (ValueError, UnicodeError):
                receipt = self.submit({"invalid": "json"}, path.stem, now)
            atomic(self.exchange / "receipts" / path.name, receipt)
            # Keep submitted content in SQLite; remove only this consumed regular inbox file.
            path.unlink()

    def export(self, now):
        view = self.view()
        export_id = identity()
        context = {"schema_version": 1, "snapshot_id": export_id, "as_of": now, **view}
        s = context["session"]
        # Bounded context; full immutable input is addressable in the server observation store.
        s["samples"] = s["samples"][-12:]
        context["features"] = {}
        if s["latest"]:
            for symbol in dict.fromkeys(
                [*domain.candidate_symbols(s), *domain.protected_symbols(s)]
            ):
                if domain.ready(symbol, s["latest"], now):
                    fast, previous, slow, score = domain.trend(
                        s["latest"]["minute"][symbol]["candles"]
                    )
                    context["features"][symbol] = {
                        "ready": True,
                        "fast_ma": str(fast),
                        "previous_fast_ma": str(previous),
                        "slow_ma": str(slow),
                        "trend_score": str(score),
                        "long_score": str(domain.long_score(symbol, s["latest"])),
                        "minute_close_at": s["latest"]["minute"][symbol]["candles"][-1]["closedAt"],
                        "daily_close_at": s["latest"]["daily"][symbol]["candles"][-1]["closedAt"],
                    }
                else:
                    context["features"][symbol] = {"ready": False}
            s["latest"]["minute"] = {}
            s["latest"]["daily"] = {}
        context["instructions"] = {
            "no_live_orders": True,
            "research_only": s["mode"] == "observer",
            "costs": "Commission only; spread, slippage, tax, FX and operation costs excluded.",
            "risk": {"position_stop_percent": 2, "holding_loss_percent": 5},
            "data_cadence": {
                "quotes_seconds": toss.QUOTE_POLL_SECONDS,
                "flat_quotes_seconds": toss.FLAT_QUOTE_POLL_SECONDS,
                "closing_quotes_seconds": toss.CLOSING_QUOTE_POLL_SECONDS,
                "history_seconds": 900,
            },
            "strategy_scope": "Registered Python modules; fixed accounting and risk envelope.",
            "strategy_workflow": (
                "tools/strategy.py scaffold -> edit code -> validate -> register -> replay "
                "-> proposal -> feedback -> revise or rollback"
            ),
            "candidate_selection": {
                "owner": "researcher",
                "proposal_schema_version": 8 if s["config"]["market"] == "GLOBAL" else 7,
                "maximum_symbols": 5,
                "required_symbols": 5 if s["config"]["market"] == "GLOBAL" else None,
                "minimum_group_size": 1,
                "maximum_group_size": 3,
                "maximum_groups": 5,
                "minimum_standing_inverse": 2,
                "required_index_inverses": 2 if s["config"]["market"] == "GLOBAL" else None,
                "review": "Reselect candidates every hourly review on the hour; no forced turnover",
                "requires": "Per-symbol rationale and evidence IDs",
                "activation": "Provider instrument validation and complete data before entry",
                "reference_universe": "Frozen benchmark only; not a candidate allowlist",
                "standing_groups": s.get("standingGroups", []),
                "standing_rules": (
                    "GLOBAL proposals select exactly five individual stocks and two daily -1x "
                    "index inverse ETFs in inverse_groups, from the inspected index catalog. "
                    "Exclude gold, bonds, ordinary ETFs and theme/sector inverses. All selected "
                    "inverses require issuer evidence; their weights and CASH may be zero. "
                    "Replacing any held stock or inverse requires an explicit zero target and "
                    "evidence-backed retirement. Seven selected slots never force seven fills. "
                    "Review downside opportunity, daily-reset risk and all execution gates."
                    if s["config"]["market"] == "GLOBAL" else
                    "Retain at least two owner-pinned inverse candidates outside the five-symbol "
                    "general quota (currently three). Do not repeat "
                    "its symbols/group IDs. Review downside opportunity each hour. Strategy plans "
                    "also admit this group; empty researcher groups allow inverse-only review. "
                    "Entry blocks may veto pinned symbols without removing monitoring. "
                    "Cash, expiry and all risk/data gates still block new entries."
                ),
            },
        }
        with self.store.transaction() as db:
            db.execute("INSERT INTO exports VALUES(?,?)", (export_id, encode(context)))
        directory = self.exchange / "exports" / export_id
        atomic(directory / "context.json", context)
        manifest = {
            "snapshot_id": export_id,
            "as_of": now,
            "sha256": hashlib.sha256(encode(context).encode()).hexdigest(),
        }
        atomic(directory / "manifest.json", manifest)
        atomic(self.exchange / "latest.json", manifest)
        self.last_export = now

    def tick(self, now, data=None):
        with self.store.transaction() as db:
            bundle = self.store.current()
            s = bundle["session"]
            active = s["lifecycle"] in ("preparing", "running")
            if active:
                if data is None:
                    data = (
                        self.demo_data(s["config"]["market"], now)
                        if s["source"] == "demo"
                        else self.collector.snapshot(now)
                        if self.collector and self.collector_id == s["id"]
                        else None
                    )
                if data:
                    db.execute(
                        "INSERT OR IGNORE INTO observations VALUES(?,?)", (data["id"], encode(data))
                    )
                for key in ("session", "benchmark"):
                    state = bundle[key]
                    native_data = (data["markets"][state["config"]["market"]]
                                   if data and data["market"] == "GLOBAL"
                                   and state["config"]["market"] != "GLOBAL" else data)
                    global_mode = state["config"]["market"] == "GLOBAL"
                    if native_data:
                        if native_data["marketOpen"] and not global_mode:
                            state["lastOpenClose"] = native_data["marketClose"]
                            if not state.get("continuousPaper"):
                                state["leaseUntil"] = min(
                                    state["leaseUntil"], native_data["marketClose"])
                        domain.ingest(
                            state,
                            native_data,
                            now,
                            baseline=key == "benchmark",
                            strategy_runner=self.strategies.run,
                        )
                    domain.sample(state, now)
                    if (
                        state.get("continuousPaper") and not global_mode
                        and data
                        and state["lifecycle"] in ("preparing", "running")
                    ):
                        closing_deadline = state.get("lastOpenClose")
                        if closing_deadline and now >= closing_deadline and state["positions"]:
                            state["lifecycle"] = "paused"
                            state["pending"] = None
                            state["version"] += 1
                            domain.gap(state, "closing_exit_incomplete", now)
                        elif not data["marketOpen"] and not state["positions"]:
                            state["leaseUntil"] = max(state["leaseUntil"] or 0, now + 86400000)
                    if global_mode and data:
                        from app.paper.global_account import lifecycle
                        lifecycle(state, data, now)
                    if (
                        state["lifecycle"] in ("preparing", "running")
                        and state["leaseUntil"]
                        and now >= state["leaseUntil"]
                    ):
                        state["lifecycle"] = "paused"
                        state["pending"] = None
                        state["version"] += 1
                        domain.gap(state, "session_lease_expired", now)
            self.store.save(bundle)
        self.inbox(now)
        if now - self.last_export >= 30000 and active:
            self.export(now)

    async def clock_loop(self):
        while True:
            try:
                async with self.lock:
                    self.tick(now_ms())
                self.last_error = None
            except Exception:
                self.last_error = "engine_tick_failed"
                # A failed engine cycle cannot continue trading unnoticed.
                async with self.lock:
                    with self.store.transaction():
                        bundle = self.store.current()
                        for s in bundle.values():
                            if s["lifecycle"] in ("preparing", "running"):
                                s["lifecycle"] = "paused"
                                s["version"] += 1
                                domain.gap(s, "engine_tick_failed", now_ms())
                        self.store.save(bundle)
            await asyncio.sleep(1)

    async def collect_once(self):
        """Collect independently of entry decisions, only during an active simulation."""
        bundle = self.store.current()
        s = bundle["session"]
        if s["source"] != "toss" or s["lifecycle"] not in ("preparing", "running"):
            return
        if self.collector_id != s["id"]:
            self.collector = (GlobalCollector() if s["config"]["market"] == "GLOBAL"
                              else Collector(s["config"]["market"]))
            self.collector_id = s["id"]
        protected = list(
            dict.fromkeys([
                *domain.protected_symbols(s),
                *domain.protected_symbols(bundle["benchmark"]),
            ])
        )
        candidates = domain.collection_symbols(s, now_ms())
        reference = domain.candidate_symbols(bundle["benchmark"])
        if s["config"]["market"] == "GLOBAL":
            reference_market = bundle["benchmark"]["config"]["market"]
            reference = [f"{reference_market}:{v}" for v in reference]
            protected = list(dict.fromkeys([
                *domain.protected_symbols(s),
                *[f"{reference_market}:{v}"
                  for v in domain.protected_symbols(bundle["benchmark"])]]))
        await self.collector.collect(protected, candidates, reference)

    async def collect_loop(self):
        while True:
            await self.collect_once()
            await asyncio.sleep(1)

    @staticmethod
    def demo_data(market, now):
        if market != "GLOBAL":
            return demo_snapshot(market, now)
        from app.paper.global_account import combine
        markets = {m: demo_snapshot(m, now) for m in ("KR", "US")}
        return combine(markets, now, markets["US"]["fx"])

    async def start(self):
        self.tasks = [
            asyncio.create_task(self.clock_loop()),
            asyncio.create_task(self.collect_loop()),
        ]

    async def close(self):
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.store.db.close()
