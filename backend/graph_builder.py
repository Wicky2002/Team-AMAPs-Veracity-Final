from __future__ import annotations

import asyncio
import os
import sys

# Required for psycopg async on Windows
if sys.platform == "win32" and hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

try:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
except Exception:  # pragma: no cover - optional dependency guard
    AsyncPostgresSaver = None
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from constants import ROUTE_END, ROUTE_END_LEGACY, ROUTE_LOOP_BACK
from graph_nodes import (
    ab_variant_node,
    content_gen_node,
    feedback_ingestor_node,
    intent_router_node,
    market_intelligence_node,
    outreach_node,
    route_after_feedback,
    route_from_intent,
)
from persistence import ensure_phase3_tables


def _build_graph():
    graph = StateGraph(dict)

    graph.add_node("intent_router", intent_router_node)
    graph.add_node("market_intelligence", market_intelligence_node)
    graph.add_node("content_generation", content_gen_node)
    graph.add_node("ab_variant", ab_variant_node)
    graph.add_node("outreach", outreach_node)
    graph.add_node("feedback_ingestor", feedback_ingestor_node)

    graph.add_edge(START, "intent_router")
    graph.add_conditional_edges(
        "intent_router",
        route_from_intent,
        {
            ROUTE_LOOP_BACK: ROUTE_LOOP_BACK,
            "content_generation": "content_generation",
            "ab_variant": "ab_variant",
            "outreach": "outreach",
            "feedback_ingestor": "feedback_ingestor",
        },
    )
    graph.add_edge("market_intelligence", "content_generation")
    graph.add_edge("content_generation", "ab_variant")
    graph.add_edge("ab_variant", "outreach")
    graph.add_edge("outreach", "feedback_ingestor")

    graph.add_conditional_edges(
        "feedback_ingestor",
        route_after_feedback,
        {
            ROUTE_LOOP_BACK: ROUTE_LOOP_BACK,
            ROUTE_END: END,
            ROUTE_END_LEGACY: END,
        },
    )

    return graph


_compiled_graph = None
_compiled_graph_lock = asyncio.Lock()
_postgres_checkpointer_cm = None
_postgres_checkpointer = None


async def reset_compiled_graph() -> None:
    """Clear cached graph/checkpointer so the next call rebuilds fresh resources."""
    global _compiled_graph
    global _postgres_checkpointer
    global _postgres_checkpointer_cm

    async with _compiled_graph_lock:
        cm = _postgres_checkpointer_cm
        _compiled_graph = None
        _postgres_checkpointer = None
        _postgres_checkpointer_cm = None

        if cm is not None and hasattr(cm, "__aexit__"):
            try:
                await cm.__aexit__(None, None, None)
            except Exception:
                # Best-effort cleanup only.
                pass


async def get_compiled_graph():
    global _compiled_graph
    global _postgres_checkpointer
    global _postgres_checkpointer_cm

    if _compiled_graph is not None:
        return _compiled_graph

    async with _compiled_graph_lock:
        if _compiled_graph is not None:
            return _compiled_graph

        graph = _build_graph()
        conn_str = os.getenv("SUPABASE_POSTGRES_URL", "").strip()

        if conn_str and AsyncPostgresSaver is not None:
            try:
                checkpointer_candidate = AsyncPostgresSaver.from_conn_string(conn_str)

                if hasattr(checkpointer_candidate, "__aenter__"):
                    _postgres_checkpointer_cm = checkpointer_candidate
                    _postgres_checkpointer = await checkpointer_candidate.__aenter__()
                else:
                    _postgres_checkpointer = checkpointer_candidate

                if hasattr(_postgres_checkpointer, "setup"):
                    await _postgres_checkpointer.setup()

                await ensure_phase3_tables()
                _compiled_graph = graph.compile(checkpointer=_postgres_checkpointer)
            except Exception:
                _compiled_graph = graph.compile(checkpointer=MemorySaver())
        else:
            _compiled_graph = graph.compile(checkpointer=MemorySaver())

        return _compiled_graph
