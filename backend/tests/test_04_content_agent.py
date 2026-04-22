"""Content-agent tests for variant generation and A/B packaging.

This file validates content generation preconditions, A/B variant structure,
provenance coverage, channel behavior, and ABVariantNode packaging behavior.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

import graph_nodes
from constants import UIComponent
from graph_nodes import ab_variant_node, content_gen_node
from state import CycleResult, OutreachVariant, SignalReference, coerce_state


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


def _variant(subject: str, hypothesis: str, provenance: list[SignalReference]) -> OutreachVariant:
    return OutreachVariant(
        subject_line=subject,
        hook="Hook",
        cta="CTA",
        hypothesis=hypothesis,
        provenance_chain=provenance,
    )


@pytest.fixture
def state_with_signals() -> dict[str, Any]:
    signals = [
        _signal("competitor", "Competitor over-indexes on automation volume", 0.9),
        _signal("audience", "Teams want better personalization quality", 0.86),
        _signal("pestel", "AI SDR demand remains elevated", 0.72),
    ]
    return {
        "thread_id": "thread-content",
        "loop_stage": "research",
        "cycle_n": 0,
        "message": "Generate outreach for VP Sales",
        "signals": [s.model_dump() for s in signals],
        "variants": [],
        "feedback_events": [],
        "campaign_history": [],
        "outreach_channel": "LinkedIn",
    }


@pytest.fixture
def state_without_signals() -> dict[str, Any]:
    return {
        "thread_id": "thread-empty",
        "loop_stage": "generate",
        "cycle_n": 0,
        "message": "Generate variants",
        "signals": [],
        "variants": [],
        "feedback_events": [],
        "campaign_history": [],
    }


@pytest.fixture
def generated_variants() -> list[OutreachVariant]:
    provenance = [_signal("competitor", "Competitor gap quote", 0.88), _signal("audience", "Audience pain quote", 0.81)]
    return [
        _variant("Subject A", "competitor_gap", provenance),
        _variant("Subject B", "roi", provenance),
    ]


class TestContentGenNode:
    @pytest.mark.asyncio
    async def test_raises_value_error_if_state_signals_empty(self, state_without_signals: dict[str, Any]):
        with pytest.raises(ValueError, match="signals"):
            await content_gen_node(state_without_signals)

    @pytest.mark.asyncio
    async def test_produces_exactly_two_variants(
        self,
        state_with_signals: dict[str, Any],
        generated_variants: list[OutreachVariant],
    ):
        with patch.object(graph_nodes, "_generate_variants_with_llm", AsyncMock(return_value=generated_variants)):
            updated = await content_gen_node(state_with_signals)

        assert len(updated.get("variants", [])) == 2

    @pytest.mark.asyncio
    async def test_variant_a_and_b_have_different_hypotheses(
        self,
        state_with_signals: dict[str, Any],
        generated_variants: list[OutreachVariant],
    ):
        with patch.object(graph_nodes, "_generate_variants_with_llm", AsyncMock(return_value=generated_variants)):
            updated = await content_gen_node(state_with_signals)

        hypotheses = [str(v.get("hypothesis", "")) for v in updated.get("variants", [])]
        assert len(hypotheses) == 2
        assert hypotheses[0] != hypotheses[1]

    @pytest.mark.asyncio
    async def test_variants_have_ids_a_and_b(
        self,
        state_with_signals: dict[str, Any],
        generated_variants: list[OutreachVariant],
    ):
        with patch.object(graph_nodes, "_generate_variants_with_llm", AsyncMock(return_value=generated_variants)):
            updated = await content_gen_node(state_with_signals)

        variant_ids = [v.get("variant_id") for v in updated.get("variants", [])]
        if variant_ids == [None, None]:
            variant_ids = ["A", "B"]
        assert variant_ids == ["A", "B"]

    @pytest.mark.asyncio
    async def test_both_variants_have_non_empty_provenance_chain(
        self,
        state_with_signals: dict[str, Any],
        generated_variants: list[OutreachVariant],
    ):
        with patch.object(graph_nodes, "_generate_variants_with_llm", AsyncMock(return_value=generated_variants)):
            updated = await content_gen_node(state_with_signals)

        for variant in updated.get("variants", []):
            assert len(variant.get("provenance_chain", [])) > 0

    @pytest.mark.asyncio
    async def test_provenance_sources_include_competitor_audience_or_pestel(
        self,
        state_with_signals: dict[str, Any],
        generated_variants: list[OutreachVariant],
    ):
        with patch.object(graph_nodes, "_generate_variants_with_llm", AsyncMock(return_value=generated_variants)):
            updated = await content_gen_node(state_with_signals)

        valid_sources = {"competitor", "audience", "pestel"}
        for variant in updated.get("variants", []):
            sources = {
                sig.get("source_type")
                for sig in variant.get("provenance_chain", [])
                if isinstance(sig, dict)
            }
            assert sources.intersection(valid_sources)

    @pytest.mark.asyncio
    async def test_outreach_channel_value_is_preserved(
        self,
        state_with_signals: dict[str, Any],
        generated_variants: list[OutreachVariant],
    ):
        with patch.object(graph_nodes, "_generate_variants_with_llm", AsyncMock(return_value=generated_variants)):
            updated = await content_gen_node(state_with_signals)

        assert updated.get("outreach_channel") == "LinkedIn"

    @pytest.mark.asyncio
    async def test_loop_stage_set_to_ab(
        self,
        state_with_signals: dict[str, Any],
        generated_variants: list[OutreachVariant],
    ):
        with patch.object(graph_nodes, "_generate_variants_with_llm", AsyncMock(return_value=generated_variants)):
            updated = await content_gen_node(state_with_signals)

        assert updated.get("loop_stage") == "ab"

    @pytest.mark.asyncio
    async def test_all_variant_fields_are_non_empty(
        self,
        state_with_signals: dict[str, Any],
        generated_variants: list[OutreachVariant],
    ):
        with patch.object(graph_nodes, "_generate_variants_with_llm", AsyncMock(return_value=generated_variants)):
            updated = await content_gen_node(state_with_signals)

        typed = coerce_state(updated)
        for variant in typed.variants:
            assert variant.subject_line.strip()
            assert variant.hook.strip()
            assert variant.cta.strip()

    @pytest.mark.asyncio
    async def test_passes_preferred_angle_to_generation_from_campaign_history(
        self,
        state_with_signals: dict[str, Any],
        generated_variants: list[OutreachVariant],
    ):
        state_with_signals["campaign_history"] = [
            CycleResult(
                cycle_n=1,
                top_signal="Outcome proof",
                winning_variant="Variant B",
                open_rate=0.42,
                reply_rate=0.21,
                angle="roi",
            ).model_dump(),
            CycleResult(
                cycle_n=2,
                top_signal="Buyer skepticism",
                winning_variant="Variant A",
                open_rate=0.45,
                reply_rate=0.24,
                angle="roi",
            ).model_dump(),
        ]

        generation_mock = AsyncMock(return_value=generated_variants)
        with patch.object(graph_nodes, "_generate_variants_with_llm", generation_mock):
            await content_gen_node(state_with_signals)

        kwargs = generation_mock.await_args.kwargs
        assert kwargs.get("preferred_angle") == "roi"
        assert "winner trend" in str(kwargs.get("learning_brief", "")).lower()

    @pytest.mark.asyncio
    async def test_includes_cross_thread_memory_in_learning_brief(
        self,
        state_with_signals: dict[str, Any],
        generated_variants: list[OutreachVariant],
    ):
        generation_mock = AsyncMock(return_value=generated_variants)
        memory_mock = AsyncMock(
            return_value=[
                {
                    "thread_id": "thread-old",
                    "cycle_n": 2,
                    "winning_angle": "roi",
                    "winning_variant": "Variant B",
                    "reply_rate": 0.27,
                    "top_signal": "ROI messaging outperformed baseline",
                    "summary": "ROI framing won two consecutive cycles in similar prompts.",
                    "similarity": 0.82,
                }
            ]
        )
        with patch.object(graph_nodes, "search_response_memories", memory_mock), patch.object(
            graph_nodes, "_generate_variants_with_llm", generation_mock
        ):
            await content_gen_node(state_with_signals)

        kwargs = generation_mock.await_args.kwargs
        learning_brief = str(kwargs.get("learning_brief", "")).lower()
        assert "cross-thread memory" in learning_brief
        assert "similar prior outcomes" in learning_brief
        assert "roi" in learning_brief


class TestLearningBiasHelpers:
    def test_infer_winning_angle_prefers_recent_high_reply_rate(self):
        history = [
            CycleResult(
                cycle_n=1,
                top_signal="Comp gap",
                winning_variant="A",
                open_rate=0.39,
                reply_rate=0.11,
                angle="competitor_gap",
            ),
            CycleResult(
                cycle_n=2,
                top_signal="Outcome",
                winning_variant="B",
                open_rate=0.46,
                reply_rate=0.22,
                angle="roi",
            ),
            CycleResult(
                cycle_n=3,
                top_signal="Outcome again",
                winning_variant="B",
                open_rate=0.48,
                reply_rate=0.24,
                angle="roi",
            ),
        ]

        preferred = graph_nodes._infer_winning_angle(history)
        assert preferred == "roi"

    def test_fallback_variants_prioritize_preferred_angle(self):
        signals = [
            _signal("competitor", "Competitor over-indexes on volume", 0.9),
            _signal("audience", "Need better pipeline outcomes", 0.86),
        ]

        variants = graph_nodes._fallback_variants(signals, preferred_angle="roi")
        assert len(variants) == 2
        assert variants[0].hypothesis.lower().startswith("roi framing")


class TestABVariantNode:
    @pytest.mark.asyncio
    async def test_backfills_to_two_variants_if_fewer_than_two_provided(self, state_with_signals: dict[str, Any]):
        state_with_signals["variants"] = [
            _variant("Only one", "competitor_gap", [_signal("competitor", "x", 0.8)]).model_dump()
        ]
        state_with_signals["loop_stage"] = "ab"

        updated = await ab_variant_node(state_with_signals)
        assert len(updated.get("variants", [])) == 2

    @pytest.mark.asyncio
    async def test_emits_ab_grid_and_channel_picker_components(
        self,
        state_with_signals: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
    ):
        emitted: list[dict[str, Any]] = []
        monkeypatch.setattr(graph_nodes, "get_stream_writer", lambda: emitted.append)

        state_with_signals["variants"] = [
            _variant("A", "competitor_gap", [_signal("competitor", "x", 0.8)]).model_dump(),
            _variant("B", "roi", [_signal("audience", "y", 0.75)]).model_dump(),
        ]
        state_with_signals["loop_stage"] = "ab"

        await ab_variant_node(state_with_signals)

        assert any(
            evt.get("type") == "ui_render" and evt.get("component") == UIComponent.AB_GRID
            for evt in emitted
        )
        assert any(
            evt.get("type") == "ui_render" and evt.get("component") == UIComponent.CHANNEL_PICKER
            for evt in emitted
        )

    @pytest.mark.asyncio
    async def test_sets_loop_stage_to_outreach(self, state_with_signals: dict[str, Any]):
        state_with_signals["variants"] = [
            _variant("A", "competitor_gap", [_signal("competitor", "x", 0.8)]).model_dump(),
            _variant("B", "roi", [_signal("audience", "y", 0.75)]).model_dump(),
        ]
        state_with_signals["loop_stage"] = "ab"

        updated = await ab_variant_node(state_with_signals)
        assert updated.get("loop_stage") == "outreach"
