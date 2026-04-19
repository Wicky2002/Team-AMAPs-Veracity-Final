from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SignalReference(BaseModel):
    source: str
    quote: str
    confidence: float


class OutreachVariant(BaseModel):
    subject_line: str
    hook: str
    cta: str
    hypothesis: str
    provenance_chain: list[SignalReference] = Field(default_factory=list)


class AgentState(BaseModel):
    loop_stage: Literal["research", "generate", "ab", "feedback"] = "research"
    message: str = ""
    signals: list[dict[str, Any]] = Field(default_factory=list)
    variants: list[OutreachVariant] = Field(default_factory=list)
    feedback_events: list[dict[str, Any]] = Field(default_factory=list)
    campaign_history: list[dict[str, Any]] = Field(default_factory=list)
    ab_results: list[dict[str, Any]] = Field(default_factory=list)
    outreach_channel: str | None = None
    selected_variant: int | None = None


def empty_agent_state(message: str = "") -> dict[str, Any]:
    return AgentState(message=message).model_dump()


def coerce_state(data: dict[str, Any]) -> AgentState:
    """Best-effort conversion from graph dict state to typed state."""
    return AgentState.model_validate(data)
