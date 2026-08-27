from __future__ import annotations

from typing import Any, Literal, TypeAlias, Union

from pydantic import BaseModel, TypeAdapter, field_validator

from constants import UI_COMPONENT_VALUES, canonicalize_ui_component


class NodeStartedEvent(BaseModel):
    type: Literal["node_started"]
    node: str
    cycle_n: int


class SignalFoundEvent(BaseModel):
    type: Literal["signal_found"]
    source: Literal["competitor", "audience", "pestel", "adjacent", "temporal", "channel"]
    content: str
    confidence: float
    quote: str


class UIRenderEvent(BaseModel):
    type: Literal["ui_render"]
    component: str
    props: dict[str, Any]
    cycle_n: int

    @field_validator("component")
    @classmethod
    def _normalize_component(cls, value: str) -> str:
        normalized = canonicalize_ui_component(value)
        if normalized is None:
            options = ", ".join(UI_COMPONENT_VALUES)
            raise ValueError(f"component must be one of: {options}")
        return normalized


class LoopCompleteEvent(BaseModel):
    type: Literal["loop_complete"]
    cycle_n: int
    next_action: Literal["awaiting_feedback", "refined_research", "end"]


class WarningEvent(BaseModel):
    type: Literal["warning"]
    message: str
    fallback_used: bool


SSEEvent: TypeAlias = Union[
    NodeStartedEvent,
    SignalFoundEvent,
    UIRenderEvent,
    LoopCompleteEvent,
    WarningEvent,
]

SSE_EVENT_ADAPTER = TypeAdapter(SSEEvent)


def normalize_event(value: dict[str, Any] | BaseModel) -> SSEEvent:
    if isinstance(value, BaseModel):
        value = value.model_dump()
    return SSE_EVENT_ADAPTER.validate_python(value)
