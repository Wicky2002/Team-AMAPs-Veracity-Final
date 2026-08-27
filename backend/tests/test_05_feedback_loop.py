"""Feedback-loop tests for ingestion, archival, and loop-closure behavior.

This file validates winner selection, winning-angle resolution, campaign
history archiving, stage transitions, conditional edge routing, and multi-cycle
integration behavior for the current implementation.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from constants import ROUTE_END, ROUTE_LOOP_BACK
from graph_nodes import feedback_ingestor_node, route_after_feedback
from state import OutreachVariant, SignalReference


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
def feedback_state_template() -> dict[str, Any]:
    return {
        "thread_id": "thread-feedback",
        "loop_stage": "feedback",
        "cycle_n": 0,
        "message": "Feedback ingestion",
        "signals": [
            _signal("competitor", "Competitor angle is too generic", 0.89).model_dump(),
            _signal("audience", "Outcome-first language resonates", 0.85).model_dump(),
        ],
        "variants": [
            {
                "subject_line": "Variant A subject",
                "hook": "Competitor gap hook",
                "cta": "CTA A",
                "hypothesis": "competitor gap framing",
                "provenance_chain": [],
            },
            {
                "subject_line": "Variant B subject",
                "hook": "ROI hook",
                "cta": "CTA B",
                "hypothesis": "roi framing",
                "provenance_chain": [],
            },
        ],
        "feedback_events": [
            {
                "note": "ROI angle resonated",
                "angle": "roi",
                "winning_variant": "Variant B",
                "open_rate": 0.48,
                "reply_rate": 0.22,
                "click_rate": 0.12,
            }
        ],
        "ab_results": [
            {"variant": 0, "open_rate": 0.44, "reply_rate": 0.11, "click_rate": 0.08},
            {"variant": 1, "open_rate": 0.48, "reply_rate": 0.22, "click_rate": 0.12},
        ],
        "campaign_history": [],
    }


class TestFeedbackIngestor:
    @pytest.mark.asyncio
    async def test_archives_cycle_result_with_feedback_metrics(self, feedback_state_template: dict[str, Any]):
        with patch("graph_nodes.load_ab_results", AsyncMock(return_value=None)):
            updated = await feedback_ingestor_node(feedback_state_template)

        history = updated.get("campaign_history", [])
        assert len(history) == 1
        latest = history[-1]
        assert float(latest.get("open_rate", 0.0)) == pytest.approx(0.48)
        assert float(latest.get("reply_rate", 0.0)) == pytest.approx(0.22)

    @pytest.mark.asyncio
    async def test_winner_selected_from_highest_reply_rate_when_winning_variant_missing(
        self,
        feedback_state_template: dict[str, Any],
    ):
        feedback_state_template["feedback_events"][0]["winning_variant"] = None
        feedback_state_template["feedback_events"][0]["angle"] = None

        with patch("graph_nodes.load_ab_results", AsyncMock(return_value=None)):
            updated = await feedback_ingestor_node(feedback_state_template)

        latest = updated.get("campaign_history", [])[-1]
        assert latest.get("winning_variant") == "Variant B subject"

    @pytest.mark.asyncio
    async def test_winning_angle_competitor_gap_when_winner_hypothesis_matches(
        self,
        feedback_state_template: dict[str, Any],
    ):
        feedback_state_template["feedback_events"][0]["angle"] = None
        feedback_state_template["feedback_events"][0]["winning_variant"] = None
        feedback_state_template["ab_results"] = [
            {"variant": 0, "open_rate": 0.45, "reply_rate": 0.25, "click_rate": 0.09},
            {"variant": 1, "open_rate": 0.48, "reply_rate": 0.18, "click_rate": 0.12},
        ]

        with patch("graph_nodes.load_ab_results", AsyncMock(return_value=None)):
            updated = await feedback_ingestor_node(feedback_state_template)

        latest = updated.get("campaign_history", [])[-1]
        assert latest.get("angle") == "competitor_gap"

    @pytest.mark.asyncio
    async def test_winning_angle_roi_when_winner_hypothesis_matches(self, feedback_state_template: dict[str, Any]):
        feedback_state_template["feedback_events"][0]["angle"] = None
        feedback_state_template["feedback_events"][0]["winning_variant"] = None
        feedback_state_template["ab_results"] = [
            {"variant": 0, "open_rate": 0.44, "reply_rate": 0.11, "click_rate": 0.08},
            {"variant": 1, "open_rate": 0.49, "reply_rate": 0.28, "click_rate": 0.13},
        ]

        with patch("graph_nodes.load_ab_results", AsyncMock(return_value=None)):
            updated = await feedback_ingestor_node(feedback_state_template)

        latest = updated.get("campaign_history", [])[-1]
        assert latest.get("angle") == "roi"

    @pytest.mark.asyncio
    async def test_loop_stage_set_to_research_when_feedback_events_present(self, feedback_state_template: dict[str, Any]):
        with patch("graph_nodes.load_ab_results", AsyncMock(return_value=None)):
            updated = await feedback_ingestor_node(feedback_state_template)

        assert updated.get("loop_stage") == "research"

    @pytest.mark.asyncio
    async def test_loop_stage_stays_feedback_when_no_feedback_events(self, feedback_state_template: dict[str, Any]):
        feedback_state_template["feedback_events"] = []

        with patch("graph_nodes.load_ab_results", AsyncMock(return_value=None)):
            updated = await feedback_ingestor_node(feedback_state_template)

        assert updated.get("loop_stage") == "feedback"

    @pytest.mark.asyncio
    async def test_cycle_n_increments_when_feedback_present(self, feedback_state_template: dict[str, Any]):
        with patch("graph_nodes.load_ab_results", AsyncMock(return_value=None)):
            updated = await feedback_ingestor_node(feedback_state_template)

        assert int(updated.get("cycle_n", 0)) == 1

    @pytest.mark.asyncio
    async def test_feedback_events_are_cleared_after_ingestion(self, feedback_state_template: dict[str, Any]):
        with patch("graph_nodes.load_ab_results", AsyncMock(return_value=None)):
            updated = await feedback_ingestor_node(feedback_state_template)

        assert updated.get("feedback_events") == []

    @pytest.mark.asyncio
    async def test_signals_and_variants_are_not_cleared_by_feedback_ingestor(self, feedback_state_template: dict[str, Any]):
        original_signals = list(feedback_state_template["signals"])
        # Normalize through the model so this stays valid as OutreachVariant gains
        # new optional fields (e.g. image_url) that model_dump() will include.
        original_variants = [
            OutreachVariant.model_validate(v).model_dump() for v in feedback_state_template["variants"]
        ]

        with patch("graph_nodes.load_ab_results", AsyncMock(return_value=None)):
            updated = await feedback_ingestor_node(feedback_state_template)

        assert updated.get("signals") == original_signals
        assert updated.get("variants") == original_variants

    @pytest.mark.asyncio
    async def test_does_not_require_ab_pair_in_state(self, feedback_state_template: dict[str, Any]):
        feedback_state_template["ab_pair"] = None

        with patch("graph_nodes.load_ab_results", AsyncMock(return_value=None)):
            updated = await feedback_ingestor_node(feedback_state_template)

        assert len(updated.get("campaign_history", [])) == 1


class TestConditionalEdge:
    def test_returns_market_intelligence_when_loop_stage_is_research(self):
        state = {"loop_stage": "research"}
        assert route_after_feedback(state) == ROUTE_LOOP_BACK

    def test_returns_end_when_loop_stage_is_not_research(self):
        state = {"loop_stage": "feedback"}
        assert route_after_feedback(state) == ROUTE_END

    @pytest.mark.asyncio
    async def test_campaign_history_not_cleared_across_two_cycles(self, feedback_state_template: dict[str, Any]):
        with patch("graph_nodes.load_ab_results", AsyncMock(return_value=None)):
            first = await feedback_ingestor_node(feedback_state_template)

        second_state = {
            **feedback_state_template,
            "cycle_n": first.get("cycle_n", 1),
            "campaign_history": first.get("campaign_history", []),
            "feedback_events": [
                {
                    "note": "Second cycle feedback",
                    "angle": "competitor_gap",
                    "winning_variant": "Variant A",
                    "open_rate": 0.46,
                    "reply_rate": 0.2,
                    "click_rate": 0.1,
                }
            ],
        }
        with patch("graph_nodes.load_ab_results", AsyncMock(return_value=None)):
            second = await feedback_ingestor_node(second_state)

        assert len(second.get("campaign_history", [])) == 2
        assert int(second.get("cycle_n", 0)) == 2
