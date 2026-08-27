from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from constants import UIComponent
from drill_down import drill_into_signal
from events import SSEEvent, UIRenderEvent, WarningEvent, normalize_event
from graph_builder import get_compiled_graph, reset_compiled_graph
from graph_nodes import reaction_counts_to_metrics
from mcp_tools.discord_channel import DiscordNotConfigured, get_message_reaction_counts
from mcp_tools.resend_channel import ResendNotConfigured, get_email_status
from persistence import save_ab_results
from state import OutreachVariant, empty_agent_state

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

app = FastAPI(title="Vector Agents - Growth Loop API")

# Allow Next.js frontend to communicate with the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LoopStartRequest(BaseModel):
    thread_id: str
    message: str
    product_name: str | None = None


class LoopActionRequest(BaseModel):
    thread_id: str
    action_type: Literal["feedback", "channel_select", "deploy_variant"] = "feedback"
    payload: dict[str, Any] = Field(default_factory=dict)
    message: str = ""


class RefreshEngagementRequest(BaseModel):
    thread_id: str


class RefreshEmailStatusRequest(BaseModel):
    thread_id: str


class DrillSignalRequest(BaseModel):
    thread_id: str
    source_type: str
    source: str
    quote: str


def _sse_line(payload: SSEEvent, event_name: str | None = None) -> str:
    body = payload.model_dump_json()
    if event_name:
        return f"event: {event_name}\ndata: {body}\n\n"
    return f"data: {body}\n\n"


def _unwrap_graph_event(event: Any) -> tuple[str, Any]:
    if isinstance(event, tuple) and len(event) == 2:
        return str(event[0]), event[1]
    return "custom", event


_TRANSIENT_CHECKPOINTER_PATTERNS: tuple[str, ...] = (
    "connection is closed",
    "server closed the connection unexpectedly",
    "consuming input failed",
    "terminating connection",
    "connection not open",
    "broken pipe",
    "could not receive data from server",
)


def _is_transient_checkpointer_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(pattern in message for pattern in _TRANSIENT_CHECKPOINTER_PATTERNS)


@app.get("/")
def read_root() -> dict[str, str]:
    return {"status": "Vector Agents API is running!"}


@app.post("/loop/start")
async def start_loop(body: LoopStartRequest):
    async def stream():
        config = {"configurable": {"thread_id": body.thread_id}}
        initial_state = empty_agent_state(
            message=body.message,
            thread_id=body.thread_id,
            product_name=body.product_name,
        )

        try:
            for attempt in range(3):
                compiled_graph = await get_compiled_graph()
                try:
                    async for event in compiled_graph.astream(
                        initial_state,
                        config=config,
                        stream_mode=["custom"],
                    ):
                        mode, payload = _unwrap_graph_event(event)
                        if mode != "custom":
                            continue
                        try:
                            typed_event = normalize_event(payload)
                        except Exception:
                            continue
                        yield _sse_line(typed_event)
                    break
                except Exception as exc:
                    if _is_transient_checkpointer_error(exc) and attempt < 2:
                        await reset_compiled_graph()
                        continue
                    raise
        except Exception as exc:
            yield _sse_line(
                WarningEvent(
                    type="warning",
                    message=f"Loop failed: {str(exc)}",
                    fallback_used=False,
                ),
                event_name="error",
            )

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/loop/action")
async def inject_action(body: LoopActionRequest):
    config = {"configurable": {"thread_id": body.thread_id}}
    update_state: dict[str, Any] = {"thread_id": body.thread_id}

    if body.message:
        update_state["message"] = body.message

    if body.action_type == "feedback":
        update_state["feedback_events"] = [body.payload or {"note": "manual feedback event"}]
        update_state["loop_stage"] = "feedback"
        update_state["route_hint"] = "feedback"
    elif body.action_type == "channel_select":
        update_state["outreach_channel"] = body.payload.get("channel", "LinkedIn")
        update_state["loop_stage"] = "outreach"
        update_state["route_hint"] = "outreach"
        update_state["outreach_requested"] = True
    elif body.action_type == "deploy_variant":
        if isinstance(body.payload.get("variant"), dict):
            update_state["selected_variant"] = body.payload.get("variant")
        update_state["loop_stage"] = "outreach"
        update_state["route_hint"] = "outreach"
        update_state["outreach_requested"] = True

    events: list[dict[str, Any]] = []
    try:
        for attempt in range(3):
            compiled_graph = await get_compiled_graph()
            try:
                # Re-entering the graph via astream() with a small partial
                # dict (e.g. just {loop_stage, route_hint, outreach_channel})
                # does NOT automatically merge onto the persisted checkpoint
                # the way a fresh /loop/start run's full initial_state does --
                # nodes would see only these few keys, with everything else
                # (signals, variants, campaign_history, ...) silently reset to
                # Pydantic defaults. Explicitly load the current checkpoint
                # and merge our partial update on top so the resumed run sees
                # the full prior state, same as refresh_engagement/drill_signal
                # already do via aget_state below.
                snapshot = await compiled_graph.aget_state(config)
                merged_state: dict[str, Any] = dict(snapshot.values) if snapshot and snapshot.values else {}
                merged_state.update(update_state)

                async for event in compiled_graph.astream(
                    merged_state,
                    config=config,
                    stream_mode=["custom"],
                ):
                    mode, payload = _unwrap_graph_event(event)
                    if mode != "custom":
                        continue
                    try:
                        typed_event = normalize_event(payload)
                        events.append(typed_event.model_dump())
                    except Exception:
                        continue
                break
            except Exception as exc:
                if _is_transient_checkpointer_error(exc) and attempt < 2:
                    await reset_compiled_graph()
                    continue
                raise
    except Exception as exc:
        warning = WarningEvent(
            type="warning",
            message=f"Action failed temporarily: {str(exc)}",
            fallback_used=True,
        )
        return {
            "status": "degraded",
            "thread_id": body.thread_id,
            "applied_action": body.action_type,
            "event_count": 1,
            "latest_events": [warning.model_dump()],
        }

    return {
        "status": "ok",
        "thread_id": body.thread_id,
        "applied_action": body.action_type,
        "event_count": len(events),
        # Every event from this action, not just the tail -- a new cycle can
        # emit 30-70+ events (research -> content_gen -> ab_variant ->
        # outreach -> feedback), and truncating to the last 10 was silently
        # dropping the ABVariantGrid/SignalIntelligenceBoard renders whenever
        # more warnings/signals landed after them in the stream (e.g. missing
        # API keys -> more fallback warnings -> truncation window shifts
        # later), leaving the frontend showing the previous cycle's stale
        # variants/images with no new render event to replace them.
        "latest_events": events,
    }


@app.post("/loop/refresh_engagement")
async def refresh_engagement(body: RefreshEngagementRequest):
    """Poll live Discord reaction counts, persist them, and return fresh
    feedback-panel metrics -- the "real-time" refresh action for the currently
    deployed variants, independent of the main graph traversal."""
    config = {"configurable": {"thread_id": body.thread_id}}
    compiled_graph = await get_compiled_graph()

    snapshot = await compiled_graph.aget_state(config)
    current_state = snapshot.values if snapshot else {}

    message_ids: list[str] = current_state.get("discord_message_ids") or []
    raw_variants = current_state.get("variants") or []
    cycle_n = int(current_state.get("cycle_n", 0))
    campaign_history = current_state.get("campaign_history") or []

    if not message_ids:
        warning = WarningEvent(
            type="warning",
            message="No Discord messages to refresh yet for this thread.",
            fallback_used=True,
        )
        return {"status": "no_messages", "thread_id": body.thread_id, "latest_events": [warning.model_dump()]}

    try:
        counts: list[int] = []
        for message_id in message_ids:
            reaction_counts = await get_message_reaction_counts(message_id=message_id)
            counts.append(sum(reaction_counts.values()))
    except DiscordNotConfigured:
        warning = WarningEvent(
            type="warning",
            message="Discord channel not configured; cannot refresh engagement.",
            fallback_used=True,
        )
        return {"status": "degraded", "thread_id": body.thread_id, "latest_events": [warning.model_dump()]}
    except Exception as exc:
        warning = WarningEvent(
            type="warning",
            message=f"Could not refresh Discord reactions: {str(exc)[:160]}",
            fallback_used=True,
        )
        return {"status": "degraded", "thread_id": body.thread_id, "latest_events": [warning.model_dump()]}

    metrics = reaction_counts_to_metrics(counts)
    variants = [OutreachVariant.model_validate(v) for v in raw_variants]

    await save_ab_results(
        thread_id=body.thread_id,
        cycle_n=cycle_n,
        variants=variants,
        metrics=metrics,
        discord_message_ids=message_ids,
    )
    # Not synced back into the graph checkpoint via aupdate_state: doing so
    # was observed to corrupt the checkpoint such that the *next* /loop/action
    # re-entry (channel_select/deploy_variant/feedback) would see the whole
    # state reset to defaults, losing signals/variants/discord_message_ids.
    # feedback_ingestor_node already reads refreshed metrics from
    # load_ab_results() (the persistence layer write above) in preference to
    # state.ab_results, so this durable save is sufficient on its own.

    event = UIRenderEvent(
        type="ui_render",
        component=UIComponent.FEEDBACK_PANEL,
        props={
            "metrics": metrics,
            "campaign_history": campaign_history,
            "discord_message_ids": message_ids,
        },
        cycle_n=cycle_n,
    )

    return {
        "status": "ok",
        "thread_id": body.thread_id,
        "latest_events": [event.model_dump()],
    }


@app.post("/loop/drill_signal")
async def drill_signal(body: DrillSignalRequest):
    """One bounded sub-investigation on a single existing signal -- doc 8.2's
    "sub-investigations when a thread branches", capped at exactly one
    follow-up hop, no recursion."""
    config = {"configurable": {"thread_id": body.thread_id}}
    compiled_graph = await get_compiled_graph()

    try:
        new_signals = await drill_into_signal(
            quote=body.quote,
            source=body.source,
            source_type=body.source_type,
        )
    except Exception as exc:
        warning = WarningEvent(
            type="warning",
            message=f"Drill-down failed: {str(exc)[:160]}",
            fallback_used=True,
        )
        return {"status": "degraded", "thread_id": body.thread_id, "latest_events": [warning.model_dump()]}

    if not new_signals:
        warning = WarningEvent(
            type="warning",
            message="Drill-down found no additional detail on this signal.",
            fallback_used=True,
        )
        return {"status": "no_results", "thread_id": body.thread_id, "latest_events": [warning.model_dump()]}

    snapshot = await compiled_graph.aget_state(config)
    current_state = snapshot.values if snapshot else {}
    existing_signals = current_state.get("signals") or []
    updated_signals = existing_signals + [s.model_dump() for s in new_signals]

    # Not synced back into the graph checkpoint via aupdate_state: doing so
    # was observed to corrupt the checkpoint such that the *next* /loop/action
    # re-entry (channel_select/deploy_variant/feedback) would see the whole
    # state reset to defaults, losing signals/variants/discord_message_ids
    # (same issue found and fixed for refresh_engagement above). The drilled
    # signals are still returned in this response's SSE events for display;
    # they just won't feed back into a later content-generation cycle.

    events: list[dict[str, Any]] = []
    for signal in new_signals:
        events.append(
            {
                "type": "signal_found",
                "source": signal.source_type,
                "content": signal.content,
                "confidence": signal.confidence,
                "quote": signal.raw_quote,
            }
        )

    board_event = UIRenderEvent(
        type="ui_render",
        component=UIComponent.SIGNAL_BOARD,
        props={
            "signals": [
                {
                    "source_type": s.get("source_type"),
                    "source": s.get("source"),
                    "source_url": s.get("source_url"),
                    "quote": s.get("quote"),
                    "raw_quote": s.get("raw_quote"),
                    "content": s.get("content"),
                    "confidence": s.get("confidence"),
                }
                for s in updated_signals
            ]
        },
        cycle_n=int(current_state.get("cycle_n", 0)),
    )
    events.append(board_event.model_dump())

    return {
        "status": "ok",
        "thread_id": body.thread_id,
        "latest_events": events,
    }


@app.post("/loop/refresh_email_status")
async def refresh_email_status(body: RefreshEmailStatusRequest):
    """Poll Resend for the real delivery/open/click status of the sent
    variant emails -- informational alongside the Discord-driven metrics that
    power winner selection, since Resend's status doesn't cleanly convert to
    the same open/reply/click-rate shape without also being sent to the same
    audience Discord reactions come from."""
    config = {"configurable": {"thread_id": body.thread_id}}
    compiled_graph = await get_compiled_graph()

    snapshot = await compiled_graph.aget_state(config)
    current_state = snapshot.values if snapshot else {}
    email_ids: list[str] = current_state.get("resend_email_ids") or []

    if not email_ids:
        warning = WarningEvent(
            type="warning",
            message="No emails sent yet for this thread.",
            fallback_used=True,
        )
        return {"status": "no_messages", "thread_id": body.thread_id, "latest_events": [warning.model_dump()]}

    statuses: list[dict[str, Any]] = []
    try:
        for idx, email_id in enumerate(email_ids):
            result = await get_email_status(email_id)
            statuses.append({"variant": idx, "email_id": email_id, "status": result.get("last_event", "unknown")})
    except ResendNotConfigured:
        warning = WarningEvent(
            type="warning",
            message="Email channel not configured; cannot refresh status.",
            fallback_used=True,
        )
        return {"status": "degraded", "thread_id": body.thread_id, "latest_events": [warning.model_dump()]}
    except Exception as exc:
        warning = WarningEvent(
            type="warning",
            message=f"Could not refresh email status: {str(exc)[:160]}",
            fallback_used=True,
        )
        return {"status": "degraded", "thread_id": body.thread_id, "latest_events": [warning.model_dump()]}

    event = UIRenderEvent(
        type="ui_render",
        component=UIComponent.FEEDBACK_PANEL,
        props={
            # No "metrics" key here on purpose: reaction metrics are only
            # ever freshly known via refresh_engagement's live Discord poll,
            # and the checkpoint's ab_results isn't kept in sync with that
            # (see refresh_engagement's comment) -- including a stale copy
            # here would clobber whatever the frontend already has whenever
            # this endpoint is refreshed after refresh_engagement.
            "campaign_history": current_state.get("campaign_history") or [],
            "discord_message_ids": current_state.get("discord_message_ids") or [],
            "resend_email_ids": email_ids,
            "email_statuses": statuses,
        },
        cycle_n=int(current_state.get("cycle_n", 0)),
    )

    return {
        "status": "ok",
        "thread_id": body.thread_id,
        "latest_events": [event.model_dump()],
    }