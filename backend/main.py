from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from events import SSEEvent, WarningEvent, normalize_event
from graph_builder import get_compiled_graph, reset_compiled_graph
from state import empty_agent_state

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


class LoopActionRequest(BaseModel):
    thread_id: str
    action_type: Literal["feedback", "channel_select", "deploy_variant"] = "feedback"
    payload: dict[str, Any] = Field(default_factory=dict)
    message: str = ""


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
        initial_state = empty_agent_state(message=body.message, thread_id=body.thread_id)

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
    elif body.action_type == "deploy_variant":
        if isinstance(body.payload.get("variant"), dict):
            update_state["selected_variant"] = body.payload.get("variant")
        update_state["loop_stage"] = "outreach"
        update_state["route_hint"] = "outreach"

    events: list[dict[str, Any]] = []
    try:
        for attempt in range(3):
            compiled_graph = await get_compiled_graph()
            try:
                async for event in compiled_graph.astream(
                    update_state,
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
        "latest_events": events[-10:],
    }