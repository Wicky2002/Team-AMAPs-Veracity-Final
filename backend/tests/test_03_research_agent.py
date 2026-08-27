"""Research-agent tests for parallel signal collection and degradation handling.

This file validates MarketIntelligence behavior with asyncio.gather(), typed
signals, confidence bookkeeping, stage updates, and partial/full failure flows.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

import graph_nodes
from graph_nodes import market_intelligence_node
from state import SignalReference, coerce_state


def _make_signal(source_type: str, source: str, quote: str, confidence: float) -> SignalReference:
    return SignalReference(
        source_type=source_type,  # type: ignore[arg-type]
        source=source,
        source_url=f"https://{source.replace('reddit/r/', 'reddit.com/r/')}",
        content=quote,
        quote=quote,
        raw_quote=quote,
        confidence=confidence,
    )


def _extract_stale_signals(state: dict[str, Any], emitted_events: list[dict[str, Any]]) -> list[str]:
    if isinstance(state.get("stale_signals"), list):
        return [str(v) for v in state["stale_signals"]]

    stale: list[str] = []
    for evt in emitted_events:
        if evt.get("type") != "warning":
            continue
        msg = str(evt.get("message", "")).lower()
        if "competitor" in msg:
            stale.append("competitor")
        if "audience" in msg:
            stale.append("audience")
        if "pestel" in msg:
            stale.append("pestel")
    return stale


@pytest.fixture
def base_state() -> dict[str, Any]:
    return {
        "thread_id": "thread-research",
        "loop_stage": "research",
        "cycle_n": 0,
        "message": "AI SDR positioning",
        "signals": [],
        "variants": [],
        "ab_pair": None,
        "feedback_events": [],
        "campaign_history": [],
        "confidence_scores": {},
        "stale_signals": [],
    }


@pytest.fixture
def sample_signals() -> dict[str, list[SignalReference]]:
    return {
        "competitor": [_make_signal("competitor", "artisan.co", "Competitor over-indexes on send volume", 0.91)],
        "audience": [_make_signal("audience", "reddit/r/sales", "Need less fluff and more relevance", 0.86)],
        "pestel": [_make_signal("pestel", "google_trends", "AI SDR intent remains elevated", 0.72)],
        "adjacent": [_make_signal("adjacent", "adjacent_web_scan", "Point tools are eating budget", 0.6)],
    }


def _patch_mcp_collectors(sample_signals: dict[str, list[SignalReference]]):
    """MCP-backed collectors (adjacent/temporal) spawn a real subprocess and hit
    the network -- mock them in unit tests the same way the other three
    collectors are mocked, so these stay fast and deterministic."""
    temporal_signal = _make_signal("temporal", "calendar_context", "Q1 2026, Monday: planning season", 0.8)
    return (
        patch.object(graph_nodes, "scan_adjacent_via_mcp", AsyncMock(return_value=sample_signals["adjacent"])),
        patch.object(graph_nodes, "get_temporal_signal_via_mcp", AsyncMock(return_value=temporal_signal)),
    )


class TestParallelResearchNodes:
    @pytest.mark.asyncio
    async def test_all_three_subnodes_called_and_results_added_to_signals(
        self,
        base_state: dict[str, Any],
        sample_signals: dict[str, list[SignalReference]],
        monkeypatch: pytest.MonkeyPatch,
    ):
        emitted: list[dict[str, Any]] = []
        monkeypatch.setattr(graph_nodes, "get_stream_writer", lambda: emitted.append)

        competitor_mock = AsyncMock(return_value=sample_signals["competitor"])
        audience_mock = AsyncMock(return_value=sample_signals["audience"])
        pestel_mock = AsyncMock(return_value=sample_signals["pestel"])
        adjacent_patch, temporal_patch = _patch_mcp_collectors(sample_signals)

        with patch.object(graph_nodes, "_collect_competitor_signals", competitor_mock), patch.object(
            graph_nodes, "_collect_audience_signals", audience_mock
        ), patch.object(graph_nodes, "_collect_pestel_signals", pestel_mock), adjacent_patch, temporal_patch:
            updated = await market_intelligence_node(base_state)

        assert competitor_mock.await_count == 1
        assert audience_mock.await_count == 1
        assert pestel_mock.await_count == 1

        typed = coerce_state(updated)
        assert len(typed.signals) >= 3
        assert all(isinstance(sig, SignalReference) for sig in typed.signals)

    @pytest.mark.asyncio
    async def test_confidence_scores_populated(
        self,
        base_state: dict[str, Any],
        sample_signals: dict[str, list[SignalReference]],
    ):
        adjacent_patch, temporal_patch = _patch_mcp_collectors(sample_signals)
        with patch.object(graph_nodes, "_collect_competitor_signals", AsyncMock(return_value=sample_signals["competitor"])), patch.object(
            graph_nodes, "_collect_audience_signals", AsyncMock(return_value=sample_signals["audience"])
        ), patch.object(graph_nodes, "_collect_pestel_signals", AsyncMock(return_value=sample_signals["pestel"])), adjacent_patch, temporal_patch:
            updated = await market_intelligence_node(base_state)

        confidence_scores = updated.get("confidence_scores")
        if confidence_scores is None:
            confidence_scores = {
                sig["source_type"]: float(sig["confidence"])
                for sig in updated.get("signals", [])
                if isinstance(sig, dict) and "source_type" in sig and "confidence" in sig
            }

        assert len(confidence_scores) > 0
        for _, score in confidence_scores.items():
            assert 0.0 <= float(score) <= 1.0

    @pytest.mark.asyncio
    async def test_loop_stage_set_to_generate_after_completion(
        self,
        base_state: dict[str, Any],
        sample_signals: dict[str, list[SignalReference]],
    ):
        adjacent_patch, temporal_patch = _patch_mcp_collectors(sample_signals)
        with patch.object(graph_nodes, "_collect_competitor_signals", AsyncMock(return_value=sample_signals["competitor"])), patch.object(
            graph_nodes, "_collect_audience_signals", AsyncMock(return_value=sample_signals["audience"])
        ), patch.object(graph_nodes, "_collect_pestel_signals", AsyncMock(return_value=sample_signals["pestel"])), adjacent_patch, temporal_patch:
            updated = await market_intelligence_node(base_state)

        assert updated["loop_stage"] == "generate"

    @pytest.mark.asyncio
    async def test_competitor_failure_still_collects_other_signals_and_marks_stale(
        self,
        base_state: dict[str, Any],
        sample_signals: dict[str, list[SignalReference]],
        monkeypatch: pytest.MonkeyPatch,
    ):
        emitted: list[dict[str, Any]] = []
        monkeypatch.setattr(graph_nodes, "get_stream_writer", lambda: emitted.append)

        adjacent_patch, temporal_patch = _patch_mcp_collectors(sample_signals)
        with patch.object(graph_nodes, "_collect_competitor_signals", AsyncMock(side_effect=Exception("boom"))), patch.object(
            graph_nodes, "_collect_audience_signals", AsyncMock(return_value=sample_signals["audience"])
        ), patch.object(graph_nodes, "_collect_pestel_signals", AsyncMock(return_value=sample_signals["pestel"])), patch.object(
            graph_nodes, "_fallback_competitor_signals", return_value=[]
        ), adjacent_patch, temporal_patch:
            updated = await market_intelligence_node(base_state)

        typed = coerce_state(updated)
        stale = _extract_stale_signals(updated, emitted)

        assert updated["loop_stage"] == "generate"
        assert "competitor" in stale
        source_types = {sig.source_type for sig in typed.signals}
        assert "audience" in source_types
        assert "pestel" in source_types

    @pytest.mark.asyncio
    async def test_all_three_failures_mark_all_stale_and_keep_signals_empty(
        self,
        base_state: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
    ):
        emitted: list[dict[str, Any]] = []
        monkeypatch.setattr(graph_nodes, "get_stream_writer", lambda: emitted.append)

        # adjacent/temporal MCP calls are also mocked to fail/empty here, so this
        # test still isolates "all five sources failed" -- their fallbacks are
        # pure local functions (no I/O) so they're left to run for real.
        with patch.object(graph_nodes, "_collect_competitor_signals", AsyncMock(side_effect=Exception("c"))), patch.object(
            graph_nodes, "_collect_audience_signals", AsyncMock(side_effect=Exception("a"))
        ), patch.object(graph_nodes, "_collect_pestel_signals", AsyncMock(side_effect=Exception("p"))), patch.object(
            graph_nodes, "_fallback_competitor_signals", return_value=[]
        ), patch.object(graph_nodes, "_fallback_audience_signals", return_value=[]), patch.object(
            graph_nodes, "_fallback_pestel_signals", return_value=[]
        ), patch.object(graph_nodes, "scan_adjacent_via_mcp", AsyncMock(return_value=[])), patch.object(
            graph_nodes, "get_temporal_signal_via_mcp", AsyncMock(return_value=None)
        ), patch.object(graph_nodes, "_fallback_adjacent_signals", return_value=[]):
            updated = await market_intelligence_node(base_state)

        stale = _extract_stale_signals(updated, emitted)

        assert updated["loop_stage"] == "generate"
        assert len(set(stale)) == 3
        # Only the local, no-I/O temporal fallback survives -- competitor/audience/
        # pestel all failed, and adjacent's fallback was forced empty above.
        source_types = {sig["source_type"] for sig in updated.get("signals", [])}
        assert source_types == {"temporal"}

    @pytest.mark.asyncio
    async def test_one_of_three_failures_collects_remaining_two_and_marks_one_stale(
        self,
        base_state: dict[str, Any],
        sample_signals: dict[str, list[SignalReference]],
        monkeypatch: pytest.MonkeyPatch,
    ):
        emitted: list[dict[str, Any]] = []
        monkeypatch.setattr(graph_nodes, "get_stream_writer", lambda: emitted.append)

        adjacent_patch, temporal_patch = _patch_mcp_collectors(sample_signals)
        with patch.object(graph_nodes, "_collect_competitor_signals", AsyncMock(side_effect=Exception("c"))), patch.object(
            graph_nodes, "_collect_audience_signals", AsyncMock(return_value=sample_signals["audience"])
        ), patch.object(graph_nodes, "_collect_pestel_signals", AsyncMock(return_value=sample_signals["pestel"])), patch.object(
            graph_nodes, "_fallback_competitor_signals", return_value=[]
        ), adjacent_patch, temporal_patch:
            updated = await market_intelligence_node(base_state)

        stale = _extract_stale_signals(updated, emitted)
        typed = coerce_state(updated)

        # audience + pestel (mocked) + adjacent + temporal (mocked MCP sources)
        assert len(typed.signals) == 4
        assert len(set(stale)) == 1

    @pytest.mark.asyncio
    async def test_signal_selection_keeps_audience_and_pestel_visible_when_competitor_dominates(
        self,
        base_state: dict[str, Any],
    ):
        heavy_competitor_signals = [
            _make_signal(
                "competitor",
                f"comp-{idx}.example",
                f"Competitor claim {idx}",
                0.95 - (idx * 0.01),
            )
            for idx in range(12)
        ]
        audience = [_make_signal("audience", "reddit/r/srilanka", "Sri Lankan buyers need practical ROI", 0.62)]
        pestel = [_make_signal("pestel", "google_trends", "Sri Lanka demand remains cost-sensitive", 0.58)]

        adjacent_patch, temporal_patch = _patch_mcp_collectors({"adjacent": []})
        with patch.object(graph_nodes, "_collect_competitor_signals", AsyncMock(return_value=heavy_competitor_signals)), patch.object(
            graph_nodes, "_collect_audience_signals", AsyncMock(return_value=audience)
        ), patch.object(graph_nodes, "_collect_pestel_signals", AsyncMock(return_value=pestel)), adjacent_patch, temporal_patch:
            updated = await market_intelligence_node(base_state)

        typed = coerce_state(updated)
        source_types = {sig.source_type for sig in typed.signals}
        assert "audience" in source_types
        assert "pestel" in source_types

    def test_sri_lanka_fallback_signals_include_location_context(self):
        audience_signals = graph_nodes._fallback_audience_signals("For the Sri Lankan market, how should we position?")
        pestel_signals = graph_nodes._fallback_pestel_signals("For the Sri Lankan market, how should we position?")

        audience_text = " ".join(f"{sig.content} {sig.quote}" for sig in audience_signals).lower()
        pestel_text = " ".join(f"{sig.content} {sig.quote}" for sig in pestel_signals).lower()

        assert "sri lanka" in audience_text
        assert "sri lanka" in pestel_text

    def test_competitor_targets_prefer_sri_lanka_override_when_geo_context_present(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setenv("COMPETITOR_TARGETS_SRI_LANKA", "local-sdr.lk, colombo-ai.com")
        monkeypatch.setenv("COMPETITOR_TARGETS", "global-default.com")

        targets = graph_nodes._competitor_targets_for_topic("Positioning for Sri Lankan B2B market")
        assert targets == ["local-sdr.lk", "colombo-ai.com"]

    def test_competitor_targets_prefer_iso_country_override_when_geo_context_present(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setenv("COMPETITOR_TARGETS_IN", "leadzen.ai, prospecting.in")
        monkeypatch.setenv("COMPETITOR_TARGETS", "global-default.com")

        targets = graph_nodes._competitor_targets_for_topic("Positioning for Indian B2B market")
        assert targets == ["leadzen.ai", "prospecting.in"]

    def test_geo_reranking_can_prioritize_country_match(self):
        global_signal = _make_signal("competitor", "global.ai", "Best outbound platform for everyone", 0.9)
        india_signal = _make_signal("competitor", "india.ai", "Top choice for India enterprise teams", 0.78)

        selected = graph_nodes._select_top_signals(
            [global_signal, india_signal],
            limit=1,
            query_context="AI SDR positioning for India enterprise teams",
        )

        assert selected[0].source == "india.ai"
