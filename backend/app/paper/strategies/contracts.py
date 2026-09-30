"""Strategy code metadata and strictly bounded decision intents."""

from decimal import Decimal
from typing import Literal

from pydantic import Field, StrictBool

from app.paper.contracts import Contract, Id, Text


class Draft(Contract):
    strategy_id: Id
    version: int = Field(ge=1, le=100000)
    parent_ref: str = Field(default="theme-top3-v1@1", max_length=120)
    name: str = Field(min_length=1, max_length=120)
    hypothesis: Text
    failure_criterion: Text
    source: str = Field(min_length=1, max_length=64000)


class Registration(Contract):
    draft: Draft
    evaluation_id: Id


class Signal(Contract):
    entry_group: str | None = Field(default=None, max_length=80)
    exits: dict[str, Literal["ma_exit", "theme_rollover", "strategy_exit"]] = Field(
        default_factory=dict, max_length=3
    )
    weights: dict[str, Decimal] = Field(default_factory=dict, max_length=3)
    rotate: StrictBool = True
    reason: str = Field(default="", max_length=500)


class Rollback(Contract):
    command_id: Id
    session_id: Id
    expected_policy_version: int = Field(ge=0)
    target_ref: str = Field(min_length=1, max_length=120)
    reason: Text
