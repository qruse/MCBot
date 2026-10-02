"""Closed contracts: proposals select admitted rules, never executable code."""

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

Id = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")]
Text = Annotated[str, Field(min_length=1, max_length=4000)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Settings(Contract):
    market: Literal["KR", "US", "GLOBAL"] = "KR"
    capital: Decimal = Field(default=Decimal("100000000"), ge=1000000, le=10**12)
    source: Literal["toss", "demo"] = "toss"
    mode: Literal["observer", "adaptive"] = "observer"


class Command(Contract):
    command_id: Id
    session_id: Id
    expected_version: int = Field(ge=0)
    action: Literal[
        "start",
        "pause",
        "resume",
        "pause_entries",
        "resume_entries",
        "new",
        "use_toss",
        "enable_continuous",
        "enable_global",
        "enable_global_preserving",
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
    market: Literal["KR", "US"] | None = None
    symbol: str = Field(pattern=r"^[A-Z0-9][A-Z0-9.\-]{0,19}$")
    name: str = Field(min_length=1, max_length=120)
    rationale: Text
    evidence_ids: list[Id] = Field(min_length=1, max_length=12)


class CandidateGroup(Contract):
    group_id: Id
    name: str = Field(min_length=1, max_length=120)
    candidates: list[Candidate] = Field(min_length=1, max_length=3)


class PortfolioPlan(Contract):
    target_weights: dict[str, Decimal] = Field(min_length=2, max_length=9)
    drift_percent: Decimal = Field(default=Decimal(2), ge=1, le=20)
    minimum_trade_krw: Decimal = Field(default=Decimal(50000), ge=10000, le=1000000)
    max_turnover_percent: Decimal = Field(default=Decimal(20), ge=1, le=25)

    @model_validator(mode="after")
    def valid_weights(self):
        values = list(self.target_weights.values())
        if (
            "CASH" not in self.target_weights
            or any(
                not x.is_finite() or x <= 0 or x >= 1 or x.as_tuple().exponent < -8 for x in values
            )
            or sum(values) != 1
        ):
            raise ValueError("invalid_portfolio_weights")
        return self


class AdaptivePortfolioPlan(PortfolioPlan):
    mode: Literal["adaptive"]
    target_weights: dict[str, Decimal] = Field(min_length=2, max_length=17)
    retirements: list[Candidate] = Field(default_factory=list, max_length=7)

    @model_validator(mode="after")
    def valid_weights(self):
        values = list(self.target_weights.values())
        if (
            "CASH" not in self.target_weights
            or self.target_weights["CASH"] < 0
            or any(
                not x.is_finite() or x < 0 or x > 1 or x.as_tuple().exponent < -8 for x in values
            )
            or sum(values) != 1
        ):
            raise ValueError("invalid_adaptive_weights")
        return self


class Proposal(Contract):
    schema_version: Literal[4, 5, 6, 7, 8] = 5
    proposal_id: Id
    run_id: Id
    session_id: Id
    snapshot_id: Id
    market: Literal["KR", "US", "GLOBAL"]
    base_policy_version: int = Field(ge=0)
    as_of: int = Field(gt=0)
    valid_from: int = Field(gt=0)
    expires_at: int = Field(gt=0)
    playbook_id: Id
    strategy_version: int = Field(default=1, ge=1, le=100000)
    allowed_symbols: list[str] = Field(max_length=6)
    candidate_groups: list[CandidateGroup] = Field(max_length=5)
    inverse_groups: list[CandidateGroup] = Field(default_factory=list, max_length=2)
    hypothesis: Text
    counterevidence: Text
    rationale: Text
    evidence: list[Evidence] = Field(max_length=12)
    experiment: Experiment | None = None
    portfolio: PortfolioPlan | AdaptivePortfolioPlan | None = None
    # Fixed envelopes cannot be expanded by the agent.
    stop_percent: Literal[2] = 2
    sidecar_percent: Literal[5] = 5
    max_exposure_percent: Decimal = Field(default=Decimal(100), ge=0, le=100)
    entry_blocks: list[str] = Field(default_factory=list, max_length=11)

    @model_validator(mode="after")
    def candidate_budget(self):
        adaptive = isinstance(self.portfolio, AdaptivePortfolioPlan)
        if (self.market == "GLOBAL") != (self.schema_version == 8):
            raise ValueError("global_requires_v8")
        if self.schema_version == 8:
            from app.paper.investment_universe import INDEX_INVERSES, inverse_key
            inverses = [item for group in self.inverse_groups for item in group.candidates]
            stocks = [item for group in self.candidate_groups for item in group.candidates]
            keys = [inverse_key(item) for item in inverses]
            if len(stocks) != 5 or len(inverses) != 2 or len(set(keys)) != 2:
                raise ValueError("fixed_five_stocks_two_index_inverses_required")
            if any(key not in INDEX_INVERSES for key in keys):
                raise ValueError("index_inverse_not_admitted")
            if not adaptive or any(
                not item.market
                for group in [*self.candidate_groups, *self.inverse_groups]
                for item in group.candidates
            ) or any(not item.market for item in self.portfolio.retirements):
                raise ValueError("global_market_required")
            if any(len({c.market for c in g.candidates}) != 1
                   for g in [*self.candidate_groups, *self.inverse_groups]):
                raise ValueError("mixed_market_group")
            inverse_ids = [g.group_id for g in self.inverse_groups]
            if len(set(inverse_ids)) != len(inverse_ids):
                raise ValueError("duplicate_candidate_groups")
        elif self.inverse_groups:
            raise ValueError("index_inverse_selection_requires_global")
        if adaptive and self.schema_version not in (7, 8):
            raise ValueError("adaptive_requires_v7")
        if self.schema_version in (7, 8) and not adaptive:
            raise ValueError("adaptive_plan_required")
        if self.portfolio and not adaptive and self.schema_version != 6:
            raise ValueError("portfolio_requires_v6")
        count = sum(len(group.candidates) for group in self.candidate_groups)
        if self.schema_version == 4:
            if len(self.candidate_groups) > 2 or any(
                len(group.candidates) != 3 for group in self.candidate_groups
            ):
                raise ValueError("v4_requires_groups_of_three")
        elif count > 5 or len(self.allowed_symbols) > 5:
            raise ValueError("general_candidate_budget_exceeded")
        return self


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
    if market == "GLOBAL":
        # GLOBAL portfolios select exactly two verified index products in each proposal.
        # Legacy native monitors survive only until their owner-requested liquidation.
        return []
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
