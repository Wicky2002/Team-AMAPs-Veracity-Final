from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from graph_nodes import (
    ab_variant_node,
    content_gen_node,
    feedback_ingestor_node,
    intent_router_node,
    market_intelligence_node,
    outreach_node,
    route_after_feedback,
)

checkpointer = MemorySaver()


def build_graph():
    graph = StateGraph(dict)

    graph.add_node("intent_router", intent_router_node)
    graph.add_node("market_intelligence", market_intelligence_node)
    graph.add_node("content_generation", content_gen_node)
    graph.add_node("ab_variant", ab_variant_node)
    graph.add_node("outreach", outreach_node)
    graph.add_node("feedback_ingestor", feedback_ingestor_node)

    graph.add_edge(START, "intent_router")
    graph.add_edge("intent_router", "market_intelligence")
    graph.add_edge("market_intelligence", "content_generation")
    graph.add_edge("content_generation", "ab_variant")
    graph.add_edge("ab_variant", "outreach")
    graph.add_edge("outreach", "feedback_ingestor")

    graph.add_conditional_edges(
        "feedback_ingestor",
        route_after_feedback,
        {
            "market_intelligence": "market_intelligence",
            "end": END,
        },
    )

    return graph.compile(checkpointer=checkpointer)


compiled_graph = build_graph()
