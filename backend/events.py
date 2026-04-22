from __future__ import annotations

from typing import Any, Literal, TypeAlias, Union

from pydantic import BaseModel, TypeAdapter


class NodeStartedEvent(BaseModel):
    type: Literal["node_started"]
    node: str
    cycle_n: int


class SignalFoundEvent(BaseModel):
    type: Literal["signal_found"]
    source: Literal["competitor", "audience", "pestel"]
    content: str
    confidence: float
    quote: str


class UIRenderEvent(BaseModel):
    type: Literal["ui_render"]
    component: Literal[
        "SignalIntelligenceBoard",
        "ABVariantGrid",
        "ChannelIntentPicker",
        "FeedbackPanel",
    ]
    props: dict[str, Any]
    cycle_n: int


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
