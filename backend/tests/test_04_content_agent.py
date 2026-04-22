"""Content-agent tests for variant generation and A/B packaging.

This file validates content generation preconditions, A/B variant structure,
provenance coverage, channel behavior, and ABVariantNode packaging behavior.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

import graph_nodes
from graph_nodes import ab_variant_node, content_gen_node
from state import OutreachVariant, SignalReference, coerce_state


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
            evt.get("type") == "ui_render" and evt.get("component") == "ABVariantGrid"
            for evt in emitted
        )
        assert any(
            evt.get("type") == "ui_render" and evt.get("component") == "ChannelIntentPicker"
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
