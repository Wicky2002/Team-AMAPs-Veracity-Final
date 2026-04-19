from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from graph_builder import compiled_graph
from state import empty_agent_state

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


def _sse_line(payload: dict[str, Any], event_name: str | None = None) -> str:
    body = json.dumps(payload, default=str)
    if event_name:
        return f"event: {event_name}\ndata: {body}\n\n"
    return f"data: {body}\n\n"


def _unwrap_graph_event(event: Any) -> tuple[str, Any]:
    if isinstance(event, tuple) and len(event) == 2:
        return str(event[0]), event[1]
    return "updates", event


@app.get("/")
def read_root() -> dict[str, str]:
    return {"status": "Vector Agents API is running!"}


@app.post("/loop/start")
async def start_loop(body: LoopStartRequest):
    async def stream():
        config = {"configurable": {"thread_id": body.thread_id}}
        initial_state = empty_agent_state(message=body.message)

        yield _sse_line(
            {
                "mode": "custom",
                "payload": {
                    "type": "loop_started",
                    "thread_id": body.thread_id,
                    "message": body.message,
                },
            }
        )

        try:
            async for event in compiled_graph.astream(
                initial_state,
                config=config,
                stream_mode=["custom", "updates"],
            ):
                mode, payload = _unwrap_graph_event(event)
                yield _sse_line({"mode": mode, "payload": payload})
        except Exception as exc:
            yield _sse_line(
                {
                    "mode": "custom",
                    "payload": {
                        "type": "error",
                        "message": str(exc),
                    },
                },
                event_name="error",
            )
        finally:
            yield _sse_line(
                {
                    "mode": "custom",
                    "payload": {
                        "type": "loop_completed",
                        "thread_id": body.thread_id,
                    },
                }
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
    update_state: dict[str, Any] = {}

    if body.message:
        update_state["message"] = body.message

    if body.action_type == "feedback":
        update_state["feedback_events"] = [body.payload or {"note": "manual feedback event"}]
    elif body.action_type == "channel_select":
        update_state["outreach_channel"] = body.payload.get("channel", "LinkedIn")
    elif body.action_type == "deploy_variant":
        update_state["selected_variant"] = body.payload.get("variant", 0)

    events: list[dict[str, Any]] = []
    async for event in compiled_graph.astream(
        update_state,
        config=config,
        stream_mode=["custom", "updates"],
    ):
        mode, payload = _unwrap_graph_event(event)
        events.append({"mode": mode, "payload": payload})

    return {
        "status": "ok",
        "thread_id": body.thread_id,
        "applied_action": body.action_type,
        "event_count": len(events),
        "latest_events": events[-3:],
    }