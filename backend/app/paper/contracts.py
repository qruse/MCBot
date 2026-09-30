"""Closed contracts: proposals select admitted rules, never executable code."""

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

Id = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")]
Text = Annotated[str, Field(min_length=1, max_length=4000)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Settings(Contract):
    market: Literal["KR", "US"] = "KR"
    capital: Decimal = Field(default=Decimal("100000000"), ge=1000000, le=10**12)
    source: Literal["toss", "demo"] = "toss"
    mode: Literal["observer", "adaptive"] = "observer"


class Command(Contract):
    command_id: Id
    session_id: Id
    expected_version: int = Field(ge=0)
    action: Literal[
        "start", "pause", "resume", "pause_entries", "resume_entries", "new", "use_toss"
    ]
    settings: Settings | None = None


class Evidence(Contract):
    evidence_id: Id
    source_url: HttpUrl
    publisher: Text
    published_at: int = Field(gt=0)
    retrieved_at: int = Field(gt=0)
    claim: Text
    excerpt: str = Field(max_length=1000)
    uncertainty: Text


class Experiment(Contract):
    experiment_id: Id
    hypothesis: Text
    failure_criterion: Text
    minimum_sessions: int = Field(ge=5, le=250)
    review_after: int = Field(gt=0)


class Candidate(Contract):
    symbol: str = Field(pattern=r"^[A-Z0-9][A-Z0-9.\-]{0,19}$")
    name: str = Field(min_length=1, max_length=120)
    rationale: Text
    evidence_ids: list[Id] = Field(min_length=1, max_length=12)


class CandidateGroup(Contract):
    group_id: Id
    name: str = Field(min_length=1, max_length=120)
    # Preserve the admitted strategy's three-stock allocation and voting thresholds.
    candidates: list[Candidate] = Field(min_length=3, max_length=3)


class Proposal(Contract):
    schema_version: Literal[4] = 4
    proposal_id: Id
    run_id: Id
    session_id: Id
    snapshot_id: Id
    market: Literal["KR", "US"]
    base_policy_version: int = Field(ge=0)
    as_of: int = Field(gt=0)
    valid_from: int = Field(gt=0)
    expires_at: int = Field(gt=0)
    playbook_id: Id
    strategy_version: int = Field(default=1, ge=1, le=100000)
    allowed_symbols: list[str] = Field(max_length=6)
    candidate_groups: list[CandidateGroup] = Field(max_length=2)
    hypothesis: Text
    counterevidence: Text
    rationale: Text
    evidence: list[Evidence] = Field(max_length=12)
    experiment: Experiment | None = None
    # Fixed envelopes cannot be expanded by the agent.
    stop_percent: Literal[2] = 2
    sidecar_percent: Literal[5] = 5
    max_exposure_percent: Decimal = Field(default=Decimal(100), ge=0, le=100)
    entry_blocks: list[str] = Field(default_factory=list, max_length=9)


THEMES = {
    "KR": {
        "kr-semis": ["005930", "000660", "042700"],
        "kr-inverse": ["114800", "252670", "123310"],
    },
    "US": {"us-semis": ["NVDA", "AVGO", "AMD"], "us-inverse": ["SH", "PSQ", "SQQQ"]},
}


def symbols(market: str) -> list[str]:
    return [symbol for group in THEMES[market].values() for symbol in group]


# User-pinned daily -1x candidates, separate from researcher quota and frozen benchmark.
STANDING_INVERSE = {
    "KR": [
        ("114800", "KODEX Inverse", "https://www.samsungfund.com/etf/search.do?searchText=114800"),
        ("123310", "TIGER Inverse", "https://www.tigeretf.com/upload/etf/20250311110104007498.pdf"),
        ("145670", "ACE Inverse", "https://www.k-etf.com/etf/145670"),
    ],
    "US": [
        (
            "SH",
            "ProShares Short S&P500",
            "https://www.proshares.com/our-etfs/leveraged-and-inverse/sh",
        ),
        (
            "PSQ",
            "ProShares Short QQQ",
            "https://www.proshares.com/our-etfs/leveraged-and-inverse/psq",
        ),
        (
            "DOG",
            "ProShares Short Dow30",
            "https://www.proshares.com/our-etfs/leveraged-and-inverse/dog",
        ),
    ],
}


def standing_groups(market: str) -> list[dict]:
    return [
        {
            "group_id": f"{market.lower()}-standing-inverse-v1",
            "name": "Standing daily -1x inverse ETFs",
            "candidates": [
                {
                    "symbol": symbol,
                    "name": name,
                    "rationale": "Owner-pinned downside candidate; conditional paper entry only.",
                    "evidence_ids": [],
                    "source_urls": [url],
                }
                for symbol, name, url in STANDING_INVERSE[market]
            ],
        }
    ]
