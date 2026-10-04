"""Local paper commands, research proposals and versioned strategy development APIs."""

import asyncio
import ipaddress
import os
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from app.paper.contracts import Command, Proposal
from app.paper.service import Conflict, PaperService, now_ms
from app.paper.strategies.contracts import Draft, Registration, Rollback
from app.paper.strategies.evaluation import replay
from app.paper.strategies.registry import check_draft
from app.paper.strategies.runtime import StrategyError

service: PaperService | None = None


def local_access(request: Request):
    # Tunnel requests that passed the remote token gate skip the local-only checks.
    if getattr(request.state, "remote_authenticated", False):
        if request.method != "GET" and request.headers.get("X-MCBot-Command") != "local-paper":
            raise HTTPException(403, "command_header_required")
        return
    origin = request.headers.get("origin")
    if request.url.hostname not in ("localhost", "127.0.0.1", "::1", "testserver"):
        raise HTTPException(403, "local_access_only")
    if origin and urlparse(origin).hostname not in ("localhost", "127.0.0.1", "::1"):
        raise HTTPException(403, "local_origin_required")
    peer = request.client.host if request.client else ""
    try:
        loopback = ipaddress.ip_address(peer).is_loopback
    except ValueError:
        loopback = peer == "testclient"
    if not loopback and os.getenv("PAPER_TRUST_LOCAL_PROXY") != "true":
        raise HTTPException(403, "local_peer_required")
    if request.method != "GET" and request.headers.get("X-MCBot-Command") != "local-paper":
        raise HTTPException(403, "command_header_required")


router = APIRouter(prefix="/paper", dependencies=[Depends(local_access)])


def current_service():
    if service is None:
        raise HTTPException(503, "paper_service_unavailable")
    return service


async def start():
    global service
    root = Path(__file__).resolve().parents[2]
    service = PaperService(
        os.getenv("PAPER_DB_PATH", str(root / ".paper" / "sessions.sqlite3")),
        os.getenv("PAPER_EXCHANGE_PATH", str(root.parent / "runtime" / "agent_exchange")),
    )
    if os.getenv("PAPER_BACKGROUND_ENABLED", "true") == "true":
        await service.start()


async def stop():
    global service
    if service:
        await service.close()
        service = None


@router.get("/snapshot")
async def snapshot():
    async with current_service().lock:
        return current_service().view()


@router.get("/sessions/{session_id}")
async def archived(session_id: str):
    try:
        return current_service().view(session_id)
    except Conflict as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/commands")
async def command(body: Command):
    try:
        async with current_service().lock:
            return current_service().command(body, now_ms())
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from exc


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")
    manual_reason: str | None = Field(default=None, min_length=1, max_length=1000)
    session_id: str | None = None
    expected_policy_version: int | None = Field(default=None, ge=0)


@router.post("/research/claim")
async def claim(body: Claim):
    try:
        async with current_service().lock:
            return current_service().claim(
                body.run_id,
                now_ms(),
                body.manual_reason,
                body.session_id,
                body.expected_policy_version,
            )
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/research/schema")
async def schema():
    return Proposal.model_json_schema()


@router.get("/strategies")
async def strategies():
    registry = current_service().strategies
    return {
        "modules": registry.catalog(),
        "evaluations": registry.evaluations(),
        "feedback": registry.feedback(),
    }


@router.get("/strategies/source")
async def strategy_source(ref: str):
    try:
        return current_service().strategies.get(ref)
    except StrategyError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/strategies/validate")
async def validate_strategy(body: Draft):
    # CPU/code execution is outside the engine lock; the writer only records the final report.
    report = await asyncio.to_thread(check_draft, body)
    async with current_service().lock:
        result = current_service().strategies.record(report, now_ms())
        current_service().export(now_ms())
        return result


@router.post("/strategies/register")
async def register_strategy(body: Registration):
    try:
        async with current_service().lock:
            result = current_service().strategies.register(body.draft, body.evaluation_id, now_ms())
            current_service().export(now_ms())
            return {key: value for key, value in result.items() if key != "source"}
    except StrategyError as exc:
        raise HTTPException(409, str(exc)) from exc


class ReplayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    strategy_ref: str = Field(min_length=1, max_length=120)
    session_id: str = Field(min_length=1, max_length=80)


@router.post("/strategies/replay")
async def replay_strategy(body: ReplayRequest):
    try:
        async with current_service().lock:
            state, inputs, modules = current_service().replay_inputs(
                body.strategy_ref, body.session_id
            )
        report = await asyncio.to_thread(replay, state, inputs, modules, body.strategy_ref)
        async with current_service().lock:
            result = current_service().strategies.record(report, now_ms())
            current_service().export(now_ms())
            return result
    except (Conflict, StrategyError) as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/strategies/rollback")
async def rollback_strategy(body: Rollback):
    try:
        async with current_service().lock:
            return current_service().rollback_strategy(body, now_ms())
    except (Conflict, StrategyError) as exc:
        raise HTTPException(409, str(exc)) from exc
