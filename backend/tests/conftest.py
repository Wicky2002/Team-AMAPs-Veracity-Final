"""Shared test fixtures.

Things that must never happen just because the test suite ran:

1. A real, billed call to the OpenAI image API
   (openai_image_gen.generate_variant_image_data_uri).
2. A real write to the Supabase database (save_ab_results /
   save_campaign_history / save_signal_cache). This bit us for real: before
   this fixture existed, every full pytest run silently wrote a row into the
   live `campaign_history` table via the "thread-feedback" fixture thread id
   -- 156 rows accumulated before anyone noticed.
3. A real, billed call to Claude for topic/competitor inference
   (_infer_topic_context, called from market_intelligence_node every cycle)
   or a real network call to the search-based competitor-discovery fallback
   (discover_competitor_domains_via_search).
4. A real, billed call to Claude for content generation
   (_generate_variants_with_llm). Individual tests in test_04_content_agent.py
   already mock this deliberately per-test; this is a session-wide backstop
   so protection doesn't depend on which test file happens to import
   graph_nodes first (and therefore cache _get_anthropic_client()'s result)
   in a given pytest run -- explicit is better than accidentally-lucky.
5. A real email send via Resend (send_variant_email) or a real status poll
   (get_email_status). Free, but a test run still shouldn't spam the real
   inbox in RESEND_TEST_RECIPIENT every time the suite runs.

All are patched here, autouse, for every test in the session -- individual
tests can still add their own more specific mocks on top without conflict.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

import graph_nodes


@pytest.fixture(autouse=True)
def _never_call_real_paid_image_api():
    with patch.object(graph_nodes, "generate_variant_image_data_uri", AsyncMock(return_value=None)):
        yield


@pytest.fixture(autouse=True)
def _never_write_to_real_database():
    with patch.object(graph_nodes, "save_ab_results", AsyncMock(return_value=None)), patch.object(
        graph_nodes, "save_campaign_history", AsyncMock(return_value=None)
    ), patch.object(graph_nodes, "save_signal_cache", AsyncMock(return_value=None)):
        yield


@pytest.fixture(autouse=True)
def _never_call_real_topic_inference():
    with patch.object(graph_nodes, "_infer_topic_context", AsyncMock(return_value=(None, [], None))), patch.object(
        graph_nodes, "discover_competitor_domains_via_search", AsyncMock(return_value=[])
    ):
        yield


@pytest.fixture(autouse=True)
def _never_call_real_content_gen_llm():
    # Only steps in if a test doesn't already patch this itself (test_04's
    # tests do, with specific return values for their assertions) -- patching
    # here too would just shadow those with the same no-op default, which is
    # harmless, but this exists specifically for tests that DON'T patch it.
    with patch.object(graph_nodes, "_generate_variants_with_llm", AsyncMock(return_value=None)):
        yield


@pytest.fixture(autouse=True)
def _never_send_real_email():
    with patch.object(graph_nodes, "send_variant_email", AsyncMock(side_effect=graph_nodes.ResendNotConfigured("test"))):
        yield
