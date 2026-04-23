from __future__ import annotations

import geo_context
from mcp_tools import audience_intel, pestel_scan


def test_detect_geo_context_for_india():
    context = geo_context.detect_geo_context("Need GTM strategy for India enterprise SDR")
    assert context is not None
    assert context.iso2 == "IN"
    assert context.country_name == "India"


def test_build_topic_query_variants_adds_country_queries():
    variants = geo_context.build_topic_query_variants("AI SDR positioning in India", max_queries=6)
    lowered = [item.lower() for item in variants]

    assert any("india" in item for item in lowered)
    assert len(variants) >= 3


def test_audience_subreddit_expansion_uses_geo_hints():
    subreddits = audience_intel._subreddits_for_topic("How should we position in India?")
    assert "india" in {item.lower() for item in subreddits}


def test_pestel_geo_params_uses_country_code():
    params = pestel_scan._geo_params_for_topic("AI SDR market trends in India")
    assert params.get("geo") == "IN"
    assert params.get("gl") == "in"
    assert params.get("hl") == "en"
