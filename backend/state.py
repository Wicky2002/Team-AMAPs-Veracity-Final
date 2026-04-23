from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


STAGE_ORDER: dict[str, int] = {
    "research": 0,
    "generate": 1,
    "ab": 2,
    "outreach": 3,
    "feedback": 4,
}


def guarded_stage_transition(current_stage: str, next_stage: str) -> str:
    """Prevent invalid backwards transitions while allowing loop reset.

    Allowed backwards transition: feedback -> research (new cycle).
    """
    if current_stage == "feedback" and next_stage == "research":
        return next_stage

    current_rank = STAGE_ORDER.get(current_stage, 0)
    next_rank = STAGE_ORDER.get(next_stage, 0)
    if next_rank < current_rank:
        raise ValueError(f"Invalid stage transition: {current_stage} -> {next_stage}")
    return next_stage


class SignalReference(BaseModel):
    source_type: Literal["competitor", "audience", "pestel"]
    source: str
    source_url: str | None = None
    content: str
    quote: str
    confidence: float
    raw_quote: str


class OutreachVariant(BaseModel):
    subject_line: str
    hook: str
    cta: str
    hypothesis: str
    provenance_chain: list[SignalReference] = Field(default_factory=list)


class FeedbackEvent(BaseModel):
    note: str = ""
    channel: Literal["LinkedIn", "Email", "Both"] | None = None
    angle: Literal["competitor_gap", "roi", "social_proof"] | None = None
    open_rate: float | None = None
    reply_rate: float | None = None
    click_rate: float | None = None
    winning_variant: str | None = None
    timestamp: str = Field(default_factory=_utc_now_iso)


class CycleResult(BaseModel):
    cycle_n: int
    top_signal: str
    winning_variant: str
    open_rate: float
    reply_rate: float
    angle: Literal["competitor_gap", "roi", "social_proof"]
    timestamp: str = Field(default_factory=_utc_now_iso)


class AgentState(BaseModel):
    thread_id: str | None = None
    loop_stage: Literal["research", "generate", "ab", "outreach", "feedback"] = "research"
    cycle_n: int = 0
    message: str = ""
    signals: list[SignalReference] = Field(default_factory=list)
    variants: list[OutreachVariant] = Field(default_factory=list)
    selected_variant: OutreachVariant | None = None
    feedback_events: list[FeedbackEvent] = Field(default_factory=list)
    campaign_history: list[CycleResult] = Field(default_factory=list)
    ab_results: list[dict[str, Any]] = Field(default_factory=list)
    outreach_channel: str | None = None

    @model_validator(mode="after")
    def stage_guards(self):
        if self.loop_stage == "generate" and not self.signals:
            raise ValueError("Cannot enter generate stage without signals")
        return self


def empty_agent_state(message: str = "", thread_id: str | None = None) -> dict[str, Any]:
    return AgentState(message=message, thread_id=thread_id).model_dump()


def coerce_state(data: dict[str, Any]) -> AgentState:
    """Best-effort conversion from graph dict state to typed state."""
    return AgentState.model_validate(data)
