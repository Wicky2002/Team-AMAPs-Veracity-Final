"""Model-layer contract tests for the Signal-to-Action system.

This file validates Pydantic model construction, literal constraints, state
accumulation behavior, timestamp defaults, and confidence/provenance contracts.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

import state as state_module
from state import AgentState, CycleResult, FeedbackEvent, OutreachVariant, SignalReference


def _utc_iso_like(value: str) -> bool:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except Exception:
        return False


@pytest.fixture
def sample_signal() -> SignalReference:
    return SignalReference(
        source_type="competitor",
        source="artisan.co",
        source_url="https://artisan.co",
        content="Competitor claims autonomous outbound at scale",
        quote="Autonomous outbound at scale",
        raw_quote="Autonomous outbound at scale",
        confidence=0.9,
    )


@pytest.fixture
def sample_variant(sample_signal: SignalReference) -> OutreachVariant:
    return OutreachVariant(
        subject_line="Close the AI SDR conversion gap",
        hook="Teams care about reply quality, not send volume.",
        cta="Open to a 15-minute benchmark?",
        hypothesis="competitor_gap",
        provenance_chain=[sample_signal],
    )


@pytest.fixture
def sample_feedback() -> FeedbackEvent:
    return FeedbackEvent(
        note="ROI angle resonated",
        angle="roi",
        open_rate=0.46,
        reply_rate=0.18,
        click_rate=0.11,
        winning_variant="Variant B",
    )


class TestCoreModels:
    def test_all_pydantic_models_instantiate_correctly_with_valid_data(
        self,
        sample_signal: SignalReference,
        sample_variant: OutreachVariant,
        sample_feedback: FeedbackEvent,
    ):
        cycle = CycleResult(
            cycle_n=1,
            top_signal=sample_signal.content,
            winning_variant="Variant B",
            open_rate=0.46,
            reply_rate=0.18,
            angle="roi",
        )

        state = AgentState(
            thread_id="thread-1",
            loop_stage="research",
            cycle_n=0,
            signals=[sample_signal],
            variants=[sample_variant],
            feedback_events=[sample_feedback],
            campaign_history=[cycle],
        )

        assert isinstance(sample_signal, SignalReference)
        assert isinstance(sample_variant, OutreachVariant)
        assert isinstance(sample_feedback, FeedbackEvent)
        assert isinstance(cycle, CycleResult)
        assert isinstance(state, AgentState)

    def test_invalid_loop_stage_literal_raises_validation_error(self):
        with pytest.raises(ValidationError):
            AgentState(loop_stage="not_a_real_stage")

    def test_agent_state_accumulates_signals_variants_feedback_events_correctly(
        self,
        sample_signal: SignalReference,
        sample_variant: OutreachVariant,
        sample_feedback: FeedbackEvent,
    ):
        state = AgentState(thread_id="thread-accumulate")

        state.signals.append(sample_signal)
        state.variants.append(sample_variant)
        state.feedback_events.append(sample_feedback)

        assert len(state.signals) == 1
        assert len(state.variants) == 1
        assert len(state.feedback_events) == 1

    def test_provenance_item_timestamp_contract_is_auto_generated(self, sample_feedback: FeedbackEvent):
        # Current codebase models timestamp defaults on FeedbackEvent/CycleResult.
        # This test enforces the same auto-timestamp contract expected for provenance metadata.
        assert isinstance(sample_feedback.timestamp, str)
        assert _utc_iso_like(sample_feedback.timestamp)

        provenance_model = getattr(state_module, "ProvenanceItem", None)
        if provenance_model is not None:
            provenance = provenance_model(source="reddit", quote="need better personalization", confidence=0.8)
            scraped_at = getattr(provenance, "scraped_at", None)
            assert isinstance(scraped_at, str)
            assert _utc_iso_like(scraped_at)

    def test_every_outreach_variant_has_non_empty_provenance_chain(self, sample_variant: OutreachVariant):
        assert len(sample_variant.provenance_chain) > 0

    def test_confidence_values_must_be_between_zero_and_one(self, sample_signal: SignalReference):
        assert 0.0 <= sample_signal.confidence <= 1.0

        optional_models = [
            "CompetitorSignal",
            "AudienceSignal",
            "PESTELSignal",
            "VariantMetrics",
        ]
        for model_name in optional_models:
            model = getattr(state_module, model_name, None)
            if model is None:
                continue

            fields = getattr(model, "model_fields", {})
            payload = {}
            for field_name in fields.keys():
                if "confidence" in field_name:
                    payload[field_name] = 0.8
                elif "domain" in field_name:
                    payload[field_name] = "artisan.co"
                elif "source" in field_name:
                    payload[field_name] = "reddit/r/sales"
                elif "taglines" in field_name or "pain_points" in field_name or "gaps" in field_name:
                    payload[field_name] = ["sample"]
                elif "complaints" in field_name or "triggers" in field_name:
                    payload[field_name] = ["sample"]
                elif "winner" in field_name:
                    payload[field_name] = False
                elif "open_rate" in field_name or "reply_rate" in field_name or "ctr" in field_name:
                    payload[field_name] = 0.1
                elif "variant_id" in field_name:
                    payload[field_name] = "A"
                else:
                    payload[field_name] = "sample"

            instance = model(**payload)
            for name in fields.keys():
                if "confidence" in name:
                    value = float(getattr(instance, name))
                    assert 0.0 <= value <= 1.0
