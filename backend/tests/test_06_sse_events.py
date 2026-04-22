"""SSE event contract tests for backend-to-frontend stream payloads.

This file validates event literals, UI component constraints, JSON
serialization, and expected node emission patterns for the current backend.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

import graph_nodes
from constants import UIComponent, UI_COMPONENT_VALUES
from events import LoopCompleteEvent, NodeStartedEvent, SignalFoundEvent, UIRenderEvent, WarningEvent, normalize_event
from graph_nodes import ab_variant_node, feedback_ingestor_node, market_intelligence_node
from state import SignalReference


def _signal(source_type: str, quote: str, confidence: float) -> SignalReference:
    return SignalReference(
        source_type=source_type,  # type: ignore[arg-type]
        source=f"{source_type}:source",
        source_url="https://example.com",
        content=quote,
        quote=quote,
        raw_quote=quote,
        confidence=confidence,
    )


@pytest.fixture
def valid_state() -> dict[str, Any]:
    return {
        "thread_id": "thread-sse",
        "loop_stage": "research",
        "cycle_n": 0,
        "message": "Research AI SDR positioning",
        "signals": [],
        "variants": [],
        "feedback_events": [],
        "campaign_history": [],
    }


class TestSSEEventModels:
    @pytest.mark.parametrize(
        "event",
        [
            NodeStartedEvent(type="node_started", node="market_intelligence", cycle_n=0),
            SignalFoundEvent(
                type="signal_found",
                source="competitor",
                content="Competitor signal",
                confidence=0.9,
                quote="Competitor signal",
            ),
            UIRenderEvent(type="ui_render", component=UIComponent.FEEDBACK_PANEL, props={}, cycle_n=0),
            LoopCompleteEvent(type="loop_complete", cycle_n=0, next_action="refined_research"),
            WarningEvent(type="warning", message="stale signal warning: cached age 24h", fallback_used=True),
        ],
    )
    def test_all_five_event_type_literals_accepted(self, event):
        normalized = normalize_event(event)
        assert normalized is not None

    def test_ui_render_raises_value_error_for_unknown_component_name(self):
        with pytest.raises(ValueError, match="component"):
            normalize_event(
                {
                    "type": "ui_render",
                    "component": "UnknownComponent",
                    "props": {},
                    "cycle_n": 0,
                }
            )

    @pytest.mark.parametrize(
        "component",
        UI_COMPONENT_VALUES,
    )
    def test_all_valid_component_names_accepted(self, component: str):
        normalized = normalize_event(
            {
                "type": "ui_render",
                "component": component,
                "props": {},
                "cycle_n": 0,
            }
        )
        assert normalized.type == "ui_render"

    def test_all_events_serialize_to_valid_json(self):
        events = [
            NodeStartedEvent(type="node_started", node="intent_router", cycle_n=0),
            SignalFoundEvent(
                type="signal_found",
                source="audience",
                content="Audience frustration with generic personalization",
                confidence=0.82,
                quote="generic personalization isn't working",
            ),
            UIRenderEvent(type="ui_render", component=UIComponent.FEEDBACK_PANEL, props={"metrics": []}, cycle_n=0),
            LoopCompleteEvent(type="loop_complete", cycle_n=1, next_action="refined_research"),
            WarningEvent(type="warning", message="stale signal warning: cached age 36h", fallback_used=True),
        ]

        for event in events:
            payload = event.model_dump_json()
            assert isinstance(payload, str)
            assert payload.startswith("{") and payload.endswith("}")


class TestSSEEmissionOrder:
    @pytest.mark.asyncio
    async def test_research_node_emits_node_started_then_signal_found_then_signal_board(
        self,
        valid_state: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
    ):
        emitted: list[dict[str, Any]] = []
        monkeypatch.setattr(graph_nodes, "get_stream_writer", lambda: emitted.append)

        competitor = [_signal("competitor", "Competitor over-indexes on volume", 0.9)]
        audience = [_signal("audience", "Need better personalization quality", 0.85)]
        pestel = [_signal("pestel", "AI SDR trend remains elevated", 0.73)]

        with patch.object(graph_nodes, "_collect_competitor_signals", AsyncMock(return_value=competitor)), patch.object(
            graph_nodes, "_collect_audience_signals", AsyncMock(return_value=audience)
        ), patch.object(graph_nodes, "_collect_pestel_signals", AsyncMock(return_value=pestel)):
            await market_intelligence_node(valid_state)

        types = [evt.get("type") for evt in emitted]
        assert "node_started" in types
        assert "signal_found" in types
        assert any(
            evt.get("type") == "ui_render" and evt.get("component") == UIComponent.SIGNAL_BOARD
            for evt in emitted
        )

        first_node_started = types.index("node_started")
        first_signal = types.index("signal_found")
        first_ui = next(
            idx
            for idx, evt in enumerate(emitted)
            if evt.get("type") == "ui_render" and evt.get("component") == UIComponent.SIGNAL_BOARD
        )
        assert first_node_started < first_signal < first_ui

    @pytest.mark.asyncio
    async def test_ab_variant_node_emits_abgrid_with_two_variants(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ):
        emitted: list[dict[str, Any]] = []
        monkeypatch.setattr(graph_nodes, "get_stream_writer", lambda: emitted.append)

        state = {
            "thread_id": "thread-ab",
            "loop_stage": "ab",
            "cycle_n": 0,
            "message": "AB",
            "signals": [
                _signal("competitor", "Gap signal", 0.9).model_dump(),
                _signal("audience", "ROI signal", 0.85).model_dump(),
            ],
            "variants": [
                {
                    "subject_line": "Subject A",
                    "hook": "Hook A",
                    "cta": "CTA A",
                    "hypothesis": "competitor_gap",
                    "provenance_chain": [_signal("competitor", "Gap signal", 0.9).model_dump()],
                },
                {
                    "subject_line": "Subject B",
                    "hook": "Hook B",
                    "cta": "CTA B",
                    "hypothesis": "roi",
                    "provenance_chain": [_signal("audience", "ROI signal", 0.85).model_dump()],
                },
            ],
            "feedback_events": [],
            "campaign_history": [],
        }

        await ab_variant_node(state)

        assert any(evt.get("type") == "node_started" for evt in emitted)
        ab_renders = [
            evt
            for evt in emitted
            if evt.get("type") == "ui_render" and evt.get("component") == UIComponent.AB_GRID
        ]
        assert len(ab_renders) == 1
        props = ab_renders[0].get("props", {})
        assert isinstance(props, dict)
        assert len(props.get("variants", [])) == 2

    @pytest.mark.asyncio
    async def test_feedback_node_emits_node_started_feedback_panel_then_loop_complete(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ):
        emitted: list[dict[str, Any]] = []
        monkeypatch.setattr(graph_nodes, "get_stream_writer", lambda: emitted.append)

        state = {
            "thread_id": "thread-feedback",
            "loop_stage": "feedback",
            "cycle_n": 0,
            "message": "feedback",
            "signals": [_signal("competitor", "Top signal", 0.9).model_dump()],
            "variants": [
                {
                    "subject_line": "A",
                    "hook": "Hook A",
                    "cta": "CTA A",
                    "hypothesis": "competitor gap",
                    "provenance_chain": [_signal("competitor", "Top signal", 0.9).model_dump()],
                },
                {
                    "subject_line": "B",
                    "hook": "Hook B",
                    "cta": "CTA B",
                    "hypothesis": "roi",
                    "provenance_chain": [_signal("audience", "Outcome signal", 0.8).model_dump()],
                },
            ],
            "feedback_events": [
                {
                    "note": "ROI won",
                    "angle": "roi",
                    "open_rate": 0.49,
                    "reply_rate": 0.19,
                    "winning_variant": "Variant B",
                }
            ],
            "campaign_history": [],
            "ab_results": [
                {"variant": 0, "open_rate": 0.43, "reply_rate": 0.11, "click_rate": 0.07},
                {"variant": 1, "open_rate": 0.49, "reply_rate": 0.19, "click_rate": 0.1},
            ],
        }

        with patch("graph_nodes.load_ab_results", AsyncMock(return_value=None)):
            await feedback_ingestor_node(state)

        types = [evt.get("type") for evt in emitted]
        assert "node_started" in types
        assert any(evt.get("type") == "ui_render" and evt.get("component") == UIComponent.FEEDBACK_PANEL for evt in emitted)
        assert "loop_complete" in types

        idx_started = types.index("node_started")
        idx_feedback = next(
            idx
            for idx, evt in enumerate(emitted)
            if evt.get("type") == "ui_render" and evt.get("component") == UIComponent.FEEDBACK_PANEL
        )
        idx_complete = types.index("loop_complete")
        assert idx_started < idx_feedback < idx_complete

    @pytest.mark.asyncio
    async def test_loop_complete_carries_current_cycle_n_and_refined_research_action(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ):
        emitted: list[dict[str, Any]] = []
        monkeypatch.setattr(graph_nodes, "get_stream_writer", lambda: emitted.append)

        state = {
            "thread_id": "thread-feedback",
            "loop_stage": "feedback",
            "cycle_n": 0,
            "message": "feedback",
            "signals": [_signal("competitor", "Top signal", 0.9).model_dump()],
            "variants": [
                {
                    "subject_line": "A",
                    "hook": "Hook A",
                    "cta": "CTA A",
                    "hypothesis": "competitor gap",
                    "provenance_chain": [_signal("competitor", "Top signal", 0.9).model_dump()],
                },
                {
                    "subject_line": "B",
                    "hook": "Hook B",
                    "cta": "CTA B",
                    "hypothesis": "roi",
                    "provenance_chain": [_signal("audience", "Outcome signal", 0.8).model_dump()],
                },
            ],
            "feedback_events": [
                {
                    "note": "ROI won",
                    "angle": "roi",
                    "open_rate": 0.49,
                    "reply_rate": 0.19,
                    "winning_variant": "Variant B",
                }
            ],
            "campaign_history": [],
            "ab_results": [
                {"variant": 0, "open_rate": 0.43, "reply_rate": 0.11, "click_rate": 0.07},
                {"variant": 1, "open_rate": 0.49, "reply_rate": 0.19, "click_rate": 0.1},
            ],
        }

        with patch("graph_nodes.load_ab_results", AsyncMock(return_value=None)):
            await feedback_ingestor_node(state)

        complete = next(evt for evt in emitted if evt.get("type") == "loop_complete")
        assert complete.get("cycle_n") == 0
        assert complete.get("next_action") == "refined_research"

    def test_warning_message_can_include_human_readable_cached_age(self):
        warning = WarningEvent(
            type="warning",
            message="stale_signal_warning: competitor cache used (cached age: 24 hours)",
            fallback_used=True,
        )
        assert "cached age" in warning.message.lower()
        assert "hours" in warning.message.lower()
