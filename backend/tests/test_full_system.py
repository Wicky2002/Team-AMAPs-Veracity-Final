"""
Full system test suite for Signal-to-Action.
Run with: py -3.11 -m pytest tests/ -v
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

# ─── SETUP ───────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import graph_nodes
from constants import UIComponent, UI_COMPONENT_VALUES
from graph_nodes import intent_router_node
from main import app
from state import AgentState, OutreachVariant, SignalReference, empty_agent_state
from intent_router import detect_intent
from events import (
    LoopCompleteEvent,
    NodeStartedEvent,
    SignalFoundEvent,
    UIRenderEvent,
    WarningEvent,
)

client = TestClient(app)


def _thread_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


@contextmanager
def _mock_graph_pipeline(*, competitor_failure: bool = False):
    """Mock graph dependencies for deterministic, fast SSE tests."""
    competitor_signals = [
        SignalReference(
            source_type="competitor",
            source="artisan.co",
            source_url="https://artisan.co",
            content="Artisan positions as autonomous AI BDR",
            quote="Hire Ava The autonomous AI BDR",
            raw_quote="Hire Ava The autonomous AI BDR",
            confidence=0.9,
        )
    ]
    audience_signals = [
        SignalReference(
            source_type="audience",
            source="reddit/r/sales",
            source_url="https://reddit.com/r/sales",
            content="Teams are tired of generic personalization",
            quote="Teams are tired of generic personalization",
            raw_quote="Teams are tired of generic personalization",
            confidence=0.86,
        )
    ]
    pestel_signals = [
        SignalReference(
            source_type="pestel",
            source="google_trends",
            source_url="https://trends.google.com",
            content="AI SDR demand remains elevated",
            quote="AI SDR demand remains elevated",
            raw_quote="AI SDR demand remains elevated",
            confidence=0.72,
        )
    ]
    generated_variants = [
        OutreachVariant(
            subject_line="Close the AI SDR conversion gap",
            hook="Most AI SDR tools optimize volume rather than reply quality.",
            cta="Open to a 15-minute gap analysis?",
            hypothesis="competitor_gap",
            provenance_chain=[],
        ),
        OutreachVariant(
            subject_line="3x better reply rates with outcome-first outreach",
            hook="Series B sales leaders are prioritizing pipeline outcomes.",
            cta="Want a quick ROI benchmark?",
            hypothesis="roi",
            provenance_chain=[],
        ),
    ]

    with ExitStack() as stack:
        if competitor_failure:
            stack.enter_context(
                patch.object(
                    graph_nodes,
                    "_collect_competitor_signals",
                    new=AsyncMock(side_effect=Exception("Connection refused")),
                )
            )
        else:
            stack.enter_context(
                patch.object(
                    graph_nodes,
                    "_collect_competitor_signals",
                    new=AsyncMock(return_value=competitor_signals),
                )
            )

        stack.enter_context(
            patch.object(
                graph_nodes,
                "_collect_audience_signals",
                new=AsyncMock(return_value=audience_signals),
            )
        )
        stack.enter_context(
            patch.object(
                graph_nodes,
                "_collect_pestel_signals",
                new=AsyncMock(return_value=pestel_signals),
            )
        )
        stack.enter_context(
            patch.object(
                graph_nodes,
                "_generate_variants_with_llm",
                new=AsyncMock(return_value=generated_variants),
            )
        )

        yield


@pytest.fixture(autouse=True)
def _stable_test_runtime(monkeypatch: pytest.MonkeyPatch):
    """Keep tests deterministic and offline-friendly where possible."""
    monkeypatch.delenv("SUPABASE_POSTGRES_URL", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with patch("intent_router._load_sentence_transformer", return_value=None):
        yield


# ─── 1. STATE MODEL TESTS ─────────────────────────────────────────────────────


class TestAgentState:
    def test_empty_state_defaults(self):
        state = empty_agent_state(message="test")
        assert state["loop_stage"] == "research"
        assert state["cycle_n"] == 0
        assert state["signals"] == []
        assert state["variants"] == []
        assert state["feedback_events"] == []
        assert state["campaign_history"] == []

    def test_signal_reference_confidence_bounds(self):
        sig = SignalReference(
            source_type="competitor",
            source="artisan.co",
            source_url="https://artisan.co",
            content="Test signal",
            quote="Test quote",
            raw_quote="Test quote",
            confidence=0.85,
        )
        assert 0.0 <= sig.confidence <= 1.0

    def test_outreach_variant_has_required_fields(self):
        variant = OutreachVariant(
            subject_line="Test subject",
            hook="Test hook",
            cta="Test CTA",
            hypothesis="competitor_gap",
            provenance_chain=[],
        )
        assert variant.subject_line
        assert variant.hook
        assert variant.cta
        assert variant.hypothesis


# ─── 2. INTENT ROUTER TESTS ───────────────────────────────────────────────────


class TestIntentRouter:
    def test_research_intent_detected(self):
        intent = detect_intent(
            "Is Lilian well-positioned in the AI SDR market?",
            current_stage="research",
        )
        assert intent == "research"

    def test_generate_intent_detected(self):
        intent = detect_intent(
            "Write three outreach variants targeting VP Sales",
            current_stage="research",
        )
        assert intent == "generate"

    def test_feedback_intent_detected(self):
        intent = detect_intent(
            "The ROI angle got 3x the reply rate",
            current_stage="outreach",
        )
        assert intent == "feedback"

    def test_ab_intent_detected(self):
        intent = detect_intent(
            "Give me a version leading with a different angle",
            current_stage="generate",
        )
        assert intent in ["ab", "generate"]

    @pytest.mark.asyncio
    async def test_route_hint_overrides_semantic(self):
        # route_hint override is enforced in intent_router_node.
        state = empty_agent_state(message="LinkedIn")
        state["loop_stage"] = "ab"
        state["route_hint"] = "outreach"

        routed = await intent_router_node(state)
        assert routed["loop_stage"] == "outreach"


# ─── 3. SSE EVENT CONTRACT TESTS ─────────────────────────────────────────────


class TestSSEEvents:
    def test_node_started_event_serializes(self):
        event = NodeStartedEvent(
            type="node_started",
            node="market_intelligence",
            cycle_n=0,
        )
        data = event.model_dump()
        assert data["type"] == "node_started"
        assert data["node"] == "market_intelligence"
        assert data["cycle_n"] == 0

    def test_signal_found_event_has_confidence(self):
        event = SignalFoundEvent(
            type="signal_found",
            source="competitor",
            content="Artisan positions as all-in-one",
            confidence=0.9,
            quote="The AI-first sales platform",
        )
        assert 0.0 <= event.confidence <= 1.0

    def test_ui_render_event_valid_component(self):
        event = UIRenderEvent(
            type="ui_render",
            component=UIComponent.AB_GRID,
            props={"variants": []},
            cycle_n=0,
        )
        valid_components = list(UI_COMPONENT_VALUES)
        assert event.component in valid_components

    def test_loop_complete_event_next_actions(self):
        event = LoopCompleteEvent(
            type="loop_complete",
            cycle_n=0,
            next_action="refined_research",
        )
        valid_actions = ["awaiting_feedback", "refined_research", "end"]
        assert event.next_action in valid_actions

    def test_warning_event_has_fallback_flag(self):
        event = WarningEvent(
            type="warning",
            message="Live competitor data unavailable — using cache",
            fallback_used=True,
        )
        assert event.fallback_used is True


# ─── 4. API ENDPOINT TESTS ────────────────────────────────────────────────────


class TestAPIEndpoints:
    def test_root_returns_ok(self):
        response = client.get("/")
        assert response.status_code == 200

    def test_loop_start_returns_event_stream(self):
        payload = {
            "thread_id": _thread_id("start"),
            "message": "Is Lilian well-positioned in the AI SDR market?",
        }
        with _mock_graph_pipeline():
            with client.stream("POST", "/loop/start", json=payload) as response:
                assert response.status_code == 200
                assert "text/event-stream" in response.headers.get("content-type", "")

                first_line = next(response.iter_lines())
                if isinstance(first_line, bytes):
                    first_line = first_line.decode("utf-8", errors="ignore")
                assert "data:" in first_line

    def test_loop_start_accepts_empty_message_current_behavior(self):
        payload = {
            "thread_id": _thread_id("empty"),
            "message": "",
        }
        with _mock_graph_pipeline():
            with client.stream("POST", "/loop/start", json=payload) as response:
                # Current implementation allows empty message and still streams events.
                assert response.status_code == 200
                assert "text/event-stream" in response.headers.get("content-type", "")

    def test_loop_action_channel_select(self):
        payload = {
            "thread_id": _thread_id("channel"),
            "action_type": "channel_select",
            "payload": {"channel": "LinkedIn"},
        }
        response = client.post("/loop/action", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"

    def test_loop_action_feedback(self):
        payload = {
            "thread_id": _thread_id("feedback"),
            "action_type": "feedback",
            "payload": {
                "note": "The ROI angle got 3x the reply rate",
                "angle": "roi",
                "reply_rate": 0.18,
                "open_rate": 0.49,
                "winning_variant": "Variant B",
            },
        }
        response = client.post("/loop/action", json=payload)
        assert response.status_code == 200
        assert response.json().get("status") == "ok"

    def test_loop_action_rejects_invalid_type(self):
        payload = {
            "thread_id": _thread_id("invalid-action"),
            "action_type": "invalid_action_xyz",
            "payload": {},
        }
        response = client.post("/loop/action", json=payload)
        assert response.status_code in [400, 422]


# ─── 5. SSE GOLDEN PATH MARKER TESTS ─────────────────────────────────────────


class TestGoldenPathSSE:
    REQUIRED_MARKERS = [
        "node_started",
        "market_intelligence",
        "competitor_node",
        "audience_node",
        "pestel_node",
        "signal_found",
        UIComponent.SIGNAL_BOARD,
        "content_gen",
        "ab_variant",
        UIComponent.AB_GRID,
        UIComponent.CHANNEL_PICKER,
        "outreach",
        UIComponent.FEEDBACK_PANEL,
        "feedback_ingestor",
        "loop_complete",
    ]

    def _collect_sse_events(
        self,
        message: str,
        *,
        max_events: int = 80,
        competitor_failure: bool = False,
    ) -> tuple[list[dict[str, Any]], set[str]]:
        payload = {
            "thread_id": _thread_id("golden"),
            "message": message,
        }
        events: list[dict[str, Any]] = []
        found_markers: set[str] = set()

        with _mock_graph_pipeline(competitor_failure=competitor_failure):
            with client.stream("POST", "/loop/start", json=payload) as response:
                if response.status_code != 200:
                    return events, found_markers

                for line in response.iter_lines():
                    if isinstance(line, bytes):
                        line = line.decode("utf-8", errors="ignore")
                    if not line:
                        continue
                    if line.startswith("data:"):
                        raw = line[5:].strip()
                        try:
                            evt = json.loads(raw)
                        except Exception:
                            continue

                        if isinstance(evt, dict):
                            events.append(evt)
                            text = json.dumps(evt)
                            for marker in self.REQUIRED_MARKERS:
                                if marker in text:
                                    found_markers.add(marker)

                    if len(events) >= max_events:
                        break

        return events, found_markers

    def test_golden_path_all_markers_present(self):
        _, found = self._collect_sse_events(
            "Is Lilian well-positioned in the AI SDR market?"
        )
        missing = [m for m in self.REQUIRED_MARKERS if m not in found]
        assert not missing, f"Missing golden path markers: {missing}"

    def test_events_are_valid_json(self):
        events, _ = self._collect_sse_events("Research Lilian positioning")
        assert len(events) > 0, "No events received"
        for evt in events:
            assert isinstance(evt, dict), f"Event is not a dict: {evt}"
            assert "type" in evt, f"Event missing 'type' field: {evt}"

    def test_cycle_n_increments_on_feedback(self):
        thread_id = _thread_id("cycle-test")
        payload_start = {
            "thread_id": thread_id,
            "message": "Research Lilian SDR positioning",
        }

        with _mock_graph_pipeline():
            # Run first cycle.
            with client.stream("POST", "/loop/start", json=payload_start) as r:
                for _ in r.iter_lines():
                    pass

            # Send feedback to trigger cycle increment.
            feedback_payload = {
                "thread_id": thread_id,
                "action_type": "feedback",
                "payload": {
                    "note": "ROI angle won",
                    "reply_rate": 0.18,
                    "open_rate": 0.42,
                    "winning_variant": "Variant B",
                    "angle": "roi",
                },
            }
            r2 = client.post("/loop/action", json=feedback_payload)
            assert r2.status_code == 200

            latest_events = r2.json().get("latest_events", [])
            cycle_ns = [
                evt.get("cycle_n")
                for evt in latest_events
                if isinstance(evt, dict) and isinstance(evt.get("cycle_n"), int)
            ]

            assert any(n >= 1 for n in cycle_ns), (
                f"cycle_n never reached 1 in feedback action events. Seen: {cycle_ns}"
            )

    def test_ui_render_events_have_valid_components(self):
        events, _ = self._collect_sse_events(
            "Write outreach variants for VP Sales targeting"
        )
        ui_events = [e for e in events if e.get("type") == "ui_render"]
        valid = set(UI_COMPONENT_VALUES)
        for evt in ui_events:
            assert evt.get("component") in valid, f"Unknown component: {evt.get('component')}"

    def test_stale_signal_fallback_emits_warning(self):
        """Simulate competitor collection failure; system should degrade gracefully."""
        events, _ = self._collect_sse_events(
            "Research competitor positioning gaps",
            competitor_failure=True,
        )
        warning_events = [e for e in events if e.get("type") == "warning"]

        assert len(events) > 0, "System crashed on scraper failure — no events received"
        assert len(warning_events) > 0, "Expected warning events on competitor failure"


# ─── 6. MCP TOOL TESTS ───────────────────────────────────────────────────────


class TestMCPTools:
    @pytest.mark.asyncio
    async def test_competitor_scraper_returns_signals(self):
        from mcp_tools.competitor_intel import scrape_competitor

        try:
            signals = await scrape_competitor("artisan.co")
        except Exception as exc:
            pytest.skip(f"Network unavailable for competitor scraper: {exc}")

        assert isinstance(signals, list)
        if signals:  # may be empty depending on network/site changes
            assert hasattr(signals[0], "raw_quote")
            assert hasattr(signals[0], "confidence")

    @pytest.mark.asyncio
    async def test_audience_intel_returns_signals(self):
        from mcp_tools.audience_intel import scan_audience_intent

        try:
            signals = await scan_audience_intent("AI SDR")
        except Exception as exc:
            pytest.skip(f"Network unavailable for audience intel: {exc}")

        assert isinstance(signals, list)

    @pytest.mark.asyncio
    async def test_signals_have_confidence_between_0_and_1(self):
        from mcp_tools.audience_intel import scan_audience_intent

        try:
            signals = await scan_audience_intent("AI sales automation")
        except Exception as exc:
            pytest.skip(f"Network unavailable for audience confidence test: {exc}")

        for sig in signals:
            assert 0.0 <= sig.confidence <= 1.0, f"Invalid confidence: {sig.confidence}"


# ─── RUN ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
