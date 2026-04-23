"""Intent-router tests for stage-aware classification behavior.

This file validates research/generate/ab/feedback intent routing, override rules,
and the 6-step demo conversation sequence contract.
"""

from __future__ import annotations

import pytest

import intent_router
from intent_router import detect_intent


@pytest.fixture(autouse=True)
def disable_sentence_transformer(monkeypatch: pytest.MonkeyPatch):
    # Keep tests deterministic and offline-friendly.
    try:
        intent_router._load_sentence_transformer.cache_clear()
    except Exception:
        pass
    monkeypatch.setattr(intent_router, "_load_sentence_transformer", lambda: None)


class TestIntentRouter:
    @pytest.mark.parametrize(
        "message",
        [
            "What's the current positioning gap in the AI SDR market?",
            "Show competitor messaging shifts in this market.",
            "What market signals should we watch this week?",
        ],
    )
    def test_research_keywords_route_to_research(self, message: str):
        assert detect_intent(message, current_stage="research") == "research"

    @pytest.mark.parametrize(
        "message",
        [
            "Write outreach copy for VP Sales personas.",
            "Create a 3-step outbound sequence.",
            "Draft a personalized outreach opener.",
        ],
    )
    def test_generate_keywords_route_to_generate(self, message: str):
        assert detect_intent(message, current_stage="research") == "generate"

    @pytest.mark.parametrize(
        "message",
        [
            "Give me a version leading with a different angle.",
            "rewrite this with a different angle and version B",
        ],
    )
    def test_ab_keywords_route_to_ab_when_stage_generate(self, message: str):
        assert detect_intent(message, current_stage="generate") == "ab"

    def test_same_variant_phrasing_routes_to_generate_when_stage_idle(self):
        message = "Write a variant for LinkedIn outreach"
        assert detect_intent(message, current_stage="idle") == "generate"

    @pytest.mark.parametrize(
        "stage",
        ["idle", "research", "generate", "ab", "outreach", "feedback"],
    )
    @pytest.mark.parametrize(
        "message",
        [
            "reply rate resonated got results",
            "The ROI angle got 3x the reply rate",
            "reply rate performed and resonated strongly",
        ],
    )
    def test_feedback_keywords_route_to_feedback_regardless_of_stage(self, stage: str, message: str):
        assert detect_intent(message, current_stage=stage) == "feedback"

    def test_feedback_keywords_override_generate_keywords_in_same_message(self):
        message = "Write outreach draft, reply rate resonated and got results"
        assert detect_intent(message, current_stage="generate") == "feedback"

    def test_exact_six_step_demo_sequence_from_brief(self):
        # Exact prompt replay from the brief, asserting CURRENT router behavior
        # for the deterministic fallback (no sentence-transformer loaded).
        prompts = [
            "What's the current positioning gap in the AI SDR market?",
            "Now write three outreach variants targeting VP Sales at Series B companies",
            "Give me a version leading with competitor gap and one leading with ROI",
            "The ROI angle got 3x the reply rate",
            "Generate the next sequence using that refined angle",
            "Actually, what's changed in competitor messaging this week?",
        ]
        expected = ["research", "research", "research", "feedback", "feedback", "feedback"]

        current_stage = "idle"
        predictions: list[str] = []
        for message in prompts:
            predicted = detect_intent(message, current_stage=current_stage)
            predictions.append(predicted)
            current_stage = predicted

        assert predictions == expected
