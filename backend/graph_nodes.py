from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Any, Literal

import httpx
from langgraph.config import get_stream_writer
from pydantic import BaseModel, Field

try:
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_ollama import ChatOllama
except Exception:  # pragma: no cover - optional dependency guard
    ChatPromptTemplate = None
    ChatOllama = None

try:
    import anthropic
    import instructor
except Exception:  # pragma: no cover - optional dependency guard
    anthropic = None
    instructor = None

from competitor_discovery import discover_competitor_domains_via_search
from constants import ROUTE_END, ROUTE_LOOP_BACK, UIComponent
from credibility import credibility_tier, domain_credibility_multiplier
from events import LoopCompleteEvent, NodeStartedEvent, SignalFoundEvent, UIRenderEvent, WarningEvent
from geo_context import detect_geo_context, get_geo_terms
from intent_router import detect_intent
from mcp_tools import (
    generate_variant_image_url,
    get_last_pestel_error,
    scan_audience_intent,
    scan_pestel_trends,
    scrape_competitor,
)
from openai_image_gen import generate_variant_image_data_uri, get_last_openai_image_error
from mcp_adjacent_client import get_temporal_signal_via_mcp, scan_adjacent_via_mcp
from mcp_tools.discord_channel import DiscordNotConfigured, post_variant_message
from mcp_tools.resend_channel import ResendNotConfigured, get_email_status, send_variant_email
from persistence import (
    load_ab_results,
    load_campaign_history,
    load_signal_cache,
    save_ab_results,
    save_campaign_history,
    save_signal_cache,
)
from state import (
    DEFAULT_PRODUCT_NAME,
    ContentPack,
    CycleResult,
    LinkedInPostCopy,
    OutreachVariant,
    SignalReference,
    coerce_state,
    guarded_stage_transition,
)


class GeneratedVariant(BaseModel):
    subject_line: str
    hook: str
    cta: str
    hypothesis: str


class ContentOutput(BaseModel):
    variants: list[GeneratedVariant] = Field(default_factory=list)
    comparison_card_title: str = Field(
        default="",
        description=(
            "A short title for the competitive-landscape comparison card, naming the actual "
            "product category (e.g. 'Sri Lankan Biscuit Brands Comparison'), not a generic phrase."
        ),
    )
    linkedin_posts: list[LinkedInPostCopy] = Field(
        default_factory=list,
        description=(
            "Exactly 3 LinkedIn post hooks with hashtags, one per angle: 'competitor_gap', "
            "'roi_outcome', 'thought_leader'. Hook is one sentence grounded in the real product/"
            "signals. Hashtags (3-4 per post) must be specific to this product's actual category "
            "and audience, not generic sales/tech hashtags."
        ),
    )
    campaign_target_audience: str = Field(
        default="",
        description="One sentence describing who actually buys/uses this specific product.",
    )
    campaign_next_actions: list[str] = Field(
        default_factory=list,
        description=(
            "3 concrete next actions appropriate to this product's actual marketing channels and "
            "category (not necessarily cold email/outbound -- could be retail, social, local promotion, etc)."
        ),
    )


class TopicAnalysis(BaseModel):
    product_or_company_name: str = Field(
        default="",
        description=(
            "The specific product, company, or brand name the query is actually about, if one is "
            "named or clearly implied. If none is named, a short neutral description of what's being "
            "discussed (e.g. 'a telecommunications provider in India')."
        ),
    )
    competitor_domains: list[str] = Field(
        default_factory=list,
        description=(
            "2-4 real, well-known direct competitor companies for this specific topic. Return their "
            "primary website domains only (e.g. 'example.com'), no other text."
        ),
    )
    product_category: Literal[
        "b2b_saas_tech",
        "consumer_fmcg",
        "local_retail_or_food_service",
        "professional_services_or_agency",
        "other_or_unclear",
    ] = Field(
        default="other_or_unclear",
        description=(
            "The business-model category this product/company actually belongs to. Use "
            "b2b_saas_tech ONLY for genuine B2B software/SaaS sold to sales/marketing/ops teams. "
            "Use consumer_fmcg for packaged consumer goods (food, beverages, household products). "
            "Use local_retail_or_food_service for brick-and-mortar retail, restaurants, or "
            "hospitality. Use professional_services_or_agency for consulting/agency/service "
            "businesses. Use other_or_unclear only if genuinely ambiguous."
        ),
    )
    content_style_note: str = Field(
        default="",
        description=(
            "One short sentence on the tone/register that would suit marketing content for this "
            "specific product (e.g. 'cold B2B outreach email register' vs. 'consumer social/"
            "retail-promotion register')."
        ),
    )


_anthropic_client = None
_anthropic_initialized = False
_last_ollama_error: str | None = None
_last_claude_error: str | None = None
_ollama_chat_llm = None
_ollama_chat_llm_config: tuple[str, str] | None = None
_last_generated_content_pack: ContentPack | None = None

# category -> (persona_line, style_hint). b2b_saas_tech intentionally
# reproduces the tool's original hardcoded persona verbatim, so the demo
# product's output is unchanged; every other category (and any failed/
# unclear classification, which maps to other_or_unclear) gets a genuinely
# different, product-appropriate register instead of always defaulting to
# B2B/cold-outreach framing.
_PERSONA_BY_CATEGORY: dict[str, tuple[str, str]] = {
    "b2b_saas_tech": (
        "You are a B2B growth expert.",
        "cold-outreach email register, ROI/pipeline framing",
    ),
    "consumer_fmcg": (
        "You are a consumer brand marketing strategist specializing in FMCG and retail growth.",
        "consumer/retail-promotion register: shelf appeal, price-value, distribution, local retail channels",
    ),
    "local_retail_or_food_service": (
        "You are a local retail and hospitality marketing strategist.",
        "consumer-facing local-promotion register: foot traffic, seasonal offers, community/local-channel tone",
    ),
    "professional_services_or_agency": (
        "You are a B2B services growth marketer.",
        "relationship/referral-driven B2B register, credibility and case-study framing",
    ),
    "other_or_unclear": (
        "You are an expert growth marketing strategist for this product's category.",
        "a tone appropriate to the product described in the user context, inferred from the live signals",
    ),
}


def _persona_for_category(category: str | None) -> tuple[str, str]:
    return _PERSONA_BY_CATEGORY.get(category or "other_or_unclear", _PERSONA_BY_CATEGORY["other_or_unclear"])


# Same problem as the text persona, one level down: the image-generation
# style suffix was hardcoded to "a laptop/phone screen showing a dashboard
# mockup" for every single generated image, regardless of product -- so a
# biscuit brand's outreach visual came back looking like SaaS UI screenshots.
_IMAGE_STYLE_BY_CATEGORY: dict[str, str] = {
    "b2b_saas_tech": (
        "Professional B2B SaaS product advertisement photography: a clean modern "
        "analytics dashboard displayed on a laptop or phone screen, studio lighting, "
        "vibrant brand accent colors, high production value social media ad campaign visual."
    ),
    "consumer_fmcg": (
        "Professional consumer packaged-goods product photography: the physical product "
        "attractively lit on a clean background or in an appetizing lifestyle setting, "
        "vibrant natural colors, high production value advertisement visual."
    ),
    "local_retail_or_food_service": (
        "Professional local retail/hospitality lifestyle photography: an inviting "
        "in-store, storefront, or dining scene with warm natural lighting, high "
        "production value local advertisement visual."
    ),
    "professional_services_or_agency": (
        "Professional corporate services photography: a clean, credible business/"
        "consulting scene (office, meeting, or handshake), polished neutral-toned "
        "advertisement visual."
    ),
    "other_or_unclear": (
        "Professional marketing product photography appropriate to the described "
        "product, clean composition, studio lighting, high production value "
        "advertisement visual."
    ),
}


def _image_style_for_category(category: str | None) -> str:
    return _IMAGE_STYLE_BY_CATEGORY.get(category or "other_or_unclear", _IMAGE_STYLE_BY_CATEGORY["other_or_unclear"])


def _set_last_content_pack(pack: ContentPack | None) -> None:
    global _last_generated_content_pack
    _last_generated_content_pack = pack


def get_last_generated_content_pack() -> ContentPack | None:
    return _last_generated_content_pack


def _get_anthropic_client():
    global _anthropic_client
    global _anthropic_initialized

    if _anthropic_initialized:
        return _anthropic_client

    _anthropic_initialized = True
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key or anthropic is None or instructor is None:
        _anthropic_client = None
        return None

    try:
        _anthropic_client = instructor.from_anthropic(anthropic.AsyncAnthropic(api_key=api_key))
    except Exception:
        _anthropic_client = None

    return _anthropic_client


def _get_llm_provider() -> Literal["auto", "anthropic", "ollama"]:
    provider = os.getenv("LLM_PROVIDER", "auto").strip().lower()
    if provider in {"anthropic", "ollama", "auto"}:
        return provider  # type: ignore[return-value]
    return "auto"


def _get_ollama_config() -> tuple[str, str] | None:
    model = os.getenv("OLLAMA_MODEL", "").strip()
    if not model:
        return None

    base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip().rstrip("/")
    if not base_url:
        base_url = "http://127.0.0.1:11434"

    return base_url, model


def _get_ollama_chat_llm(*, base_url: str, model: str):
    global _ollama_chat_llm
    global _ollama_chat_llm_config

    if ChatOllama is None:
        return None

    config = (base_url, model)
    if _ollama_chat_llm is None or _ollama_chat_llm_config != config:
        _ollama_chat_llm = ChatOllama(
            model=model,
            base_url=base_url,
            temperature=0.2,
        )
        _ollama_chat_llm_config = config

    return _ollama_chat_llm


def _extract_llm_content_text(response: Any) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts).strip()

    return str(content).strip()


def _strip_markdown_fences(raw: str) -> str:
    text = (raw or "").strip()
    if not text.startswith("```"):
        return text

    lines = text.splitlines()
    if lines:
        lines = lines[1:]

    while lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]

    return "\n".join(lines).strip()


def _loads_json_object(raw: str) -> dict[str, Any]:
    cleaned = _strip_markdown_fences(raw)
    try:
        payload = json.loads(cleaned)
    except Exception:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end <= start:
            raise
        payload = json.loads(cleaned[start : end + 1])

    if not isinstance(payload, dict):
        raise ValueError("LLM JSON response is not an object")
    return payload


def _content_pack_from_structured(structured: ContentOutput) -> ContentPack | None:
    """Extract the LLM-generated comparison-card/LinkedIn/campaign-brief copy
    from a validated ContentOutput. Returns None if the LLM didn't actually
    fill any of it in (older/degraded responses), so callers fall back to
    the builder functions' own generic (non-AI-SDR) defaults."""
    if not (
        structured.comparison_card_title
        or structured.linkedin_posts
        or structured.campaign_target_audience
        or structured.campaign_next_actions
    ):
        return None
    return ContentPack(
        comparison_card_title=structured.comparison_card_title.strip(),
        linkedin_posts=structured.linkedin_posts,
        campaign_target_audience=structured.campaign_target_audience.strip(),
        campaign_next_actions=[a.strip() for a in structured.campaign_next_actions if a.strip()],
    )


def _variants_from_structured_output(structured: ContentOutput) -> list[OutreachVariant]:
    variants: list[OutreachVariant] = []
    for item in structured.variants[:2]:
        subject_line = item.subject_line.strip()
        hook = item.hook.strip()
        cta = item.cta.strip()
        hypothesis = item.hypothesis.strip()
        if not (subject_line and hook and cta):
            continue

        variants.append(
            OutreachVariant(
                subject_line=subject_line,
                hook=hook,
                cta=cta,
                hypothesis=hypothesis or "Outcome-aligned framing",
                provenance_chain=[],
            )
        )

    return variants


def _set_last_ollama_error(message: str | None) -> None:
    global _last_ollama_error
    cleaned = (message or "").strip()
    _last_ollama_error = cleaned or None


def _set_last_claude_error(message: str | None) -> None:
    global _last_claude_error
    cleaned = (message or "").strip()
    _last_claude_error = cleaned or None


def _describe_llm_failure(provider: Literal["auto", "anthropic", "ollama"]) -> str | None:
    details: list[str] = []

    if provider in {"auto", "ollama"} and _last_ollama_error:
        details.append(f"ollama={_last_ollama_error}")
    if provider in {"auto", "anthropic"} and _last_claude_error:
        details.append(f"anthropic={_last_claude_error}")

    if not details:
        return None
    return "; ".join(details)[:480]


def _emit(event: NodeStartedEvent | SignalFoundEvent | UIRenderEvent | LoopCompleteEvent | WarningEvent) -> None:
    """Emit streaming events when graph runs in custom stream mode."""
    try:
        writer = get_stream_writer()
        writer(event.model_dump())
    except Exception:
        # Safe no-op when stream writer is unavailable.
        pass


def _to_signal_card(signal: SignalReference) -> dict[str, Any]:
    return {
        "source_type": signal.source_type,
        "source": signal.source,
        "source_url": signal.source_url,
        "quote": signal.quote,
        "raw_quote": signal.raw_quote,
        "content": signal.content,
        "confidence": signal.confidence,
        "credibility_tier": credibility_tier(signal.source_url),
    }


def _to_angle(hypothesis: str) -> Literal["competitor_gap", "roi", "social_proof"]:
    lowered = (hypothesis or "").lower()
    if "roi" in lowered:
        return "roi"
    if "social" in lowered:
        return "social_proof"
    return "competitor_gap"


def _angle_prompt_name(angle: Literal["competitor_gap", "roi", "social_proof"]) -> str:
    labels = {
        "competitor_gap": "competitor gap angle",
        "roi": "ROI/outcome angle",
        "social_proof": "social proof angle",
    }
    return labels.get(angle, "competitor gap angle")


def _preferred_variant_angles(
    preferred_angle: Literal["competitor_gap", "roi", "social_proof"] | None,
) -> tuple[
    Literal["competitor_gap", "roi", "social_proof"],
    Literal["competitor_gap", "roi", "social_proof"],
]:
    if preferred_angle == "roi":
        return "roi", "competitor_gap"
    if preferred_angle == "social_proof":
        return "social_proof", "competitor_gap"
    return "competitor_gap", "roi"


def _infer_winning_angle(
    campaign_history: list[CycleResult],
) -> Literal["competitor_gap", "roi", "social_proof"] | None:
    if not campaign_history:
        return None

    recent = campaign_history[-5:]
    angle_scores: dict[Literal["competitor_gap", "roi", "social_proof"], float] = {
        "competitor_gap": 0.0,
        "roi": 0.0,
        "social_proof": 0.0,
    }

    total = len(recent)
    for idx, result in enumerate(recent):
        recency_weight = 1.0 + (idx / max(1, total - 1)) * 0.5
        reply_rate = max(float(result.reply_rate), 0.0)
        open_rate = max(float(result.open_rate), 0.0)
        performance_score = max(reply_rate, open_rate * 0.35, 0.01)
        angle_scores[result.angle] += recency_weight * performance_score

    preferred_angle = max(angle_scores, key=angle_scores.get)
    if angle_scores[preferred_angle] <= 0:
        return None
    return preferred_angle


def _build_learning_brief(
    campaign_history: list[CycleResult],
    preferred_angle: Literal["competitor_gap", "roi", "social_proof"] | None,
) -> str:
    if not campaign_history or preferred_angle is None:
        return "No prior campaign winners available yet."

    recent = campaign_history[-5:]
    wins = [cycle for cycle in recent if cycle.angle == preferred_angle]
    avg_reply_rate = sum(float(cycle.reply_rate) for cycle in wins) / max(1, len(wins))
    latest = recent[-1]

    return (
        f"Recent winner trend: {_angle_prompt_name(preferred_angle)} "
        f"({len(wins)}/{len(recent)} recent cycles, avg reply rate {avg_reply_rate * 100:.1f}%). "
        f"Latest winner: '{latest.winning_variant}' with {_angle_prompt_name(latest.angle)}."
    )


def _copy_signal(signal: SignalReference) -> SignalReference:
    return SignalReference.model_validate(signal.model_dump())


def _signal_search_text(signal: SignalReference) -> str:
    return " ".join(
        [
            signal.source_type,
            signal.source,
            signal.source_url or "",
            signal.content,
            signal.quote,
            signal.raw_quote,
        ]
    ).lower()


def _normalized_terms(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]{3,}", (text or "").lower())}


def _geo_match_score(signal: SignalReference, query_context: str) -> float:
    geo = detect_geo_context(query_context)
    if geo is None:
        return 0.6

    signal_text = _signal_search_text(signal)
    terms = get_geo_terms(query_context)
    if any(term in signal_text for term in terms):
        return 1.0
    return 0.2


def _source_quality_score(signal: SignalReference) -> float:
    base_scores = {
        "competitor": 0.78,
        "audience": 0.72,
        "pestel": 0.74,
        "adjacent": 0.68,
        "temporal": 0.7,
        "channel": 0.75,
    }
    base = base_scores.get(signal.source_type, 0.65)
    return min(1.0, base * domain_credibility_multiplier(signal.source_url))


def _recency_score(signal: SignalReference) -> float:
    url = (signal.source_url or "").lower()
    if not url:
        return 0.5

    years = [int(match) for match in re.findall(r"20\d{2}", url)]
    if not years:
        return 0.55

    latest = max(years)
    if latest >= 2025:
        return 0.9
    if latest >= 2023:
        return 0.75
    return 0.6


def _corroboration_score(signal: SignalReference, all_signals: list[SignalReference]) -> float:
    this_terms = _normalized_terms(f"{signal.raw_quote} {signal.content}")
    if not this_terms:
        return 0.4

    strongest_overlap = 0
    for other in all_signals:
        if other is signal or other.source_type == signal.source_type:
            continue

        other_terms = _normalized_terms(f"{other.raw_quote} {other.content}")
        overlap = len(this_terms.intersection(other_terms))
        strongest_overlap = max(strongest_overlap, overlap)

    if strongest_overlap >= 4:
        return 0.95
    if strongest_overlap >= 2:
        return 0.8
    if strongest_overlap >= 1:
        return 0.65
    return 0.4


def _signal_rank_score(signal: SignalReference, all_signals: list[SignalReference], query_context: str) -> float:
    relevance = max(0.0, min(float(signal.confidence), 1.0))
    geo_match = _geo_match_score(signal, query_context)
    source_quality = _source_quality_score(signal)
    recency = _recency_score(signal)
    corroboration = _corroboration_score(signal, all_signals)

    return (
        0.35 * relevance
        + 0.25 * geo_match
        + 0.20 * source_quality
        + 0.10 * recency
        + 0.10 * corroboration
    )


def _select_top_signals(
    signals: list[SignalReference],
    limit: int = 5,
    query_context: str = "",
) -> list[SignalReference]:
    if limit <= 0:
        return []

    ranked = sorted(
        signals,
        key=lambda sig: _signal_rank_score(sig, signals, query_context),
        reverse=True,
    )
    selected: list[SignalReference] = []

    # Keep cross-source visibility so one source cannot crowd out the board.
    for source_type in ("competitor", "audience", "pestel", "adjacent", "temporal"):
        preferred = next((sig for sig in ranked if sig.source_type == source_type and sig not in selected), None)
        if preferred is not None:
            selected.append(preferred)
        if len(selected) >= limit:
            return selected[:limit]

    for signal in ranked:
        if signal in selected:
            continue
        selected.append(signal)
        if len(selected) >= limit:
            break

    return selected[:limit]


def _fallback_competitor_signals(message: str) -> list[SignalReference]:
    # No fabricated market claim here on purpose: if live competitor
    # discovery/scraping found nothing, the honest result is "no competitor
    # signal this cycle" -- the caller emits a visible warning instead of
    # this function inventing a plausible-sounding but made-up sentence.
    return []


def _fallback_pestel_signals(message: str = "") -> list[SignalReference]:
    return []


def _fallback_audience_signals(message: str = "") -> list[SignalReference]:
    return []


def _fallback_adjacent_signals(message: str = "") -> list[SignalReference]:
    return []


def _fallback_temporal_signal() -> SignalReference:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    quarter = (now.month - 1) // 3 + 1
    signal_text = f"Q{quarter} {now.year}, {now.strftime('%A')}: seasonal buying-cycle context unavailable."
    return SignalReference(
        source_type="temporal",
        source="calendar_context",
        source_url=None,
        content=signal_text,
        quote=signal_text,
        confidence=0.6,
        raw_quote=signal_text,
    )


def _parse_competitor_domains(raw: str) -> list[str]:
    candidates = [part.strip() for part in (raw or "").split(",")]
    cleaned = [item for item in candidates if item]

    deduped: list[str] = []
    seen: set[str] = set()
    for domain in cleaned:
        normalized = domain.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(domain)
    return deduped


async def _infer_topic_context(message: str) -> tuple[str | None, list[str], TopicAnalysis | None]:
    """One Claude call, run once per research cycle: infer the actual
    product/company the query is about (so the UI's product-name field isn't
    stuck on its default), real competitor domains for that topic (so
    research doesn't scrape an unrelated hardcoded list), and the product's
    business-model category (so content generation doesn't default to a
    B2B-SaaS persona/tone for every product). Returns (None, [], None) on
    any failure -- callers already have their own fallback for each part."""
    client = _get_anthropic_client()
    if client is None or not message.strip():
        return None, [], None

    prompt = f"""Analyze this query about a product, company, or market:

"{message}"

Identify what specific product/company/market this is actually about, name
2-4 real, well-known direct competitors for it, and classify its business-model
category and the marketing content style/tone that would actually suit it.
"""
    try:
        result = await client.messages.create(
            model="claude-sonnet-5",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
            response_model=TopicAnalysis,
        )
    except Exception:
        return None, [], None

    name = result.product_or_company_name.strip() or None
    domains = [d.strip() for d in result.competitor_domains if d.strip()][:4]
    return name, domains, result


def _competitor_targets_for_topic(topic: str, discovered_domains: list[str] | None = None) -> list[str]:
    """Resolve which domains to scrape for competitor signal. Priority order:
    explicit geo-specific env override > explicit generic env override >
    dynamically discovered domains for this topic > the hardcoded default
    list (last resort, so research never comes back completely empty)."""
    geo = detect_geo_context(topic)
    if geo is not None:
        country_targets = _parse_competitor_domains(os.getenv(f"COMPETITOR_TARGETS_{geo.iso2}", ""))
        if country_targets:
            return country_targets

        # Backward compatibility for previous Sri Lanka-specific env key.
        if geo.iso2 == "LK":
            sri_lanka_targets = _parse_competitor_domains(os.getenv("COMPETITOR_TARGETS_SRI_LANKA", ""))
            if sri_lanka_targets:
                return sri_lanka_targets

    override_targets = _parse_competitor_domains(os.getenv("COMPETITOR_TARGETS", ""))
    if override_targets:
        return override_targets

    if discovered_domains:
        return discovered_domains

    # No hardcoded last-resort list here on purpose: falling back to a fixed
    # set of unrelated companies (the tool's original demo competitors) would
    # silently misrepresent the market for any other product. Callers treat
    # an empty result as "no competitor signal this cycle" and warn instead.
    return []


def _fallback_variant_for_angle(
    angle: Literal["competitor_gap", "roi", "social_proof"],
    *,
    competitor_quote: str,
    outcome_quote: str,
    product_name: str = "This product",
) -> OutreachVariant:
    if angle == "roi":
        return OutreachVariant(
            subject_line=f"A practical path to better results with {product_name}",
            hook=f"Buyers now care most about outcomes and attribution — {outcome_quote[:140]}",
            cta="Want the ROI playbook we use with our best customers?",
            hypothesis=f"ROI framing should win with buyers focused on predictable, measurable results from {product_name}.",
            provenance_chain=[],
        )

    if angle == "social_proof":
        return OutreachVariant(
            subject_line=f"How peer teams are getting more from {product_name}",
            hook=f"Top teams respond faster to concrete proof over claims — {outcome_quote[:140]}",
            cta="Want 3 real examples we can adapt to your outreach this week?",
            hypothesis="Social proof framing should reduce skepticism by showing credible peer outcomes.",
            provenance_chain=[],
        )

    return OutreachVariant(
        subject_line=f"The gap most {product_name} buyers are still paying for",
        hook=f"Most tools in this space optimize the wrong thing — {competitor_quote[:140]}",
        cta="Open to a 15-minute gap analysis this week?",
        hypothesis=f"Competitor gap framing will create urgency by naming an avoidable risk {product_name} solves.",
        provenance_chain=[],
    )


def _fallback_variants(
    top_signals: list[SignalReference],
    *,
    preferred_angle: Literal["competitor_gap", "roi", "social_proof"] | None = None,
    product_name: str = "This product",
) -> list[OutreachVariant]:
    competitor_quote = next(
        (s.raw_quote for s in top_signals if s.source_type == "competitor"),
        "Competitors in this space over-index on volume rather than outcomes",
    )
    outcome_quote = next(
        (s.raw_quote for s in top_signals if s.source_type in {"audience", "pestel"}),
        "Buyers are prioritizing measurable outcomes over feature lists",
    )

    first_angle, second_angle = _preferred_variant_angles(preferred_angle)

    return [
        _fallback_variant_for_angle(
            first_angle, competitor_quote=competitor_quote, outcome_quote=outcome_quote, product_name=product_name
        ),
        _fallback_variant_for_angle(
            second_angle, competitor_quote=competitor_quote, outcome_quote=outcome_quote, product_name=product_name
        ),
    ]


def _signal_matches_quote(signal: SignalReference, quote: str) -> bool:
    signal_text = f"{signal.raw_quote} {signal.content}".lower()
    quote_text = (quote or "").lower()
    if not signal_text or not quote_text:
        return False
    return any(token in signal_text for token in quote_text.split()[:4] if len(token) > 3)


def _provenance_for_variant(
    variant: OutreachVariant,
    top_signals: list[SignalReference],
    *,
    index: int,
) -> list[SignalReference]:
    if variant.provenance_chain:
        return [_copy_signal(sig) for sig in variant.provenance_chain[:4]]

    matched = [sig for sig in top_signals if _signal_matches_quote(sig, variant.hook)]
    if matched:
        return [_copy_signal(sig) for sig in matched[:4]]

    if index == 0:
        preferred = [sig for sig in top_signals if sig.source_type == "competitor"]
    else:
        preferred = [sig for sig in top_signals if sig.source_type in {"audience", "pestel"}]

    if not preferred:
        preferred = list(top_signals)

    return [_copy_signal(sig) for sig in preferred[:4]]


def _enrich_variants(
    variants: list[OutreachVariant],
    top_signals: list[SignalReference],
    *,
    preferred_angle: Literal["competitor_gap", "roi", "social_proof"] | None = None,
    product_name: str = "This product",
) -> list[OutreachVariant]:
    defaults = (
        "Competitor gap framing will create urgency around differentiation.",
        "ROI framing will resonate with VP Sales outcome ownership.",
    )

    enriched: list[OutreachVariant] = []
    for idx, variant in enumerate(variants[:2]):
        hypothesis = (variant.hypothesis or "").strip() or defaults[min(idx, len(defaults) - 1)]
        enriched.append(
            OutreachVariant(
                subject_line=variant.subject_line,
                hook=variant.hook,
                cta=variant.cta,
                hypothesis=hypothesis,
                provenance_chain=_provenance_for_variant(variant, top_signals, index=idx),
            )
        )

    fallback_pool = _fallback_variants(top_signals, preferred_angle=preferred_angle, product_name=product_name)
    while len(enriched) < 2:
        fallback_variant = fallback_pool[len(enriched)]
        enriched.append(
            OutreachVariant(
                subject_line=fallback_variant.subject_line,
                hook=fallback_variant.hook,
                cta=fallback_variant.cta,
                hypothesis=fallback_variant.hypothesis,
                provenance_chain=_provenance_for_variant(fallback_variant, top_signals, index=len(enriched)),
            )
        )

    return enriched


async def _collect_competitor_signals(topic: str, discovered_domains: list[str] | None = None) -> list[SignalReference]:
    signals: list[SignalReference] = []
    for domain in _competitor_targets_for_topic(topic, discovered_domains):
        cached = await load_signal_cache(domain=domain, topic=topic)
        if cached:
            signals.extend(cached)
            continue

        scraped = await scrape_competitor(domain)
        if scraped:
            signals.extend(scraped)
            await save_signal_cache(domain=domain, topic=topic, signals=scraped)
    return signals


async def _collect_audience_signals(topic: str, product_category: str | None = None) -> list[SignalReference]:
    cache_key = "reddit_audience"
    cached = await load_signal_cache(domain=cache_key, topic=topic)
    if cached:
        return cached

    scanned = await scan_audience_intent(topic, product_category=product_category)
    if scanned:
        await save_signal_cache(domain=cache_key, topic=topic, signals=scanned)
    return scanned


async def _collect_pestel_signals(topic: str) -> list[SignalReference]:
    cache_key = "pestel_serpapi"
    cached = await load_signal_cache(domain=cache_key, topic=topic)
    if cached:
        return cached

    scanned = await scan_pestel_trends(topic)
    if scanned:
        await save_signal_cache(domain=cache_key, topic=topic, signals=scanned)
    return scanned


async def _generate_variants_with_claude(
    *,
    message: str,
    top_signals: list[SignalReference],
    learning_brief: str | None = None,
    preferred_angle: Literal["competitor_gap", "roi", "social_proof"] | None = None,
    product_name: str = "the product",
    persona_line: str = "You are a B2B growth expert.",
    style_hint: str = "cold-outreach email register, ROI/pipeline framing",
) -> list[OutreachVariant] | None:
    _set_last_claude_error(None)
    client = _get_anthropic_client()
    if client is None:
        _set_last_claude_error("Anthropic client unavailable (missing/invalid ANTHROPIC_API_KEY or dependency)")
        return None

    signals_text = "\n".join([f"- [{s.source_type}] {s.raw_quote}" for s in top_signals])
    angle_a, angle_b = _preferred_variant_angles(preferred_angle)
    history_context = learning_brief or "No prior campaign winners available yet."

    prompt = f"""{persona_line} Write in {style_hint}. Based on these live market signals about the market {product_name} competes in:

{signals_text}

Historical performance memory:
{history_context}

Generate 2 outreach email variants for {product_name} targeting the buyers most likely to purchase it.

Variant A: Lead with {_angle_prompt_name(angle_a)}
Variant B: Lead with {_angle_prompt_name(angle_b)}

If historical memory indicates a winning angle, bias your framing toward it unless current signals strongly contradict it.

Each variant must include: subject_line, hook (first sentence), cta, hypothesis.
Keep each field concise and specific.

Also produce, all grounded in the real product/signals above (not generic sales/tech language):
- comparison_card_title: a short title naming the actual competitive category.
- linkedin_posts: exactly 3 posts (angles competitor_gap, roi_outcome, thought_leader), each with a one-sentence hook and 3-4 hashtags relevant to this specific product's category and audience.
- campaign_target_audience: one sentence on who actually buys/uses this product.
- campaign_next_actions: 3 concrete next actions appropriate to this product's actual marketing channels.

User context: {message}
"""

    try:
        result = await client.messages.create(
            model="claude-sonnet-5",
            max_tokens=2000,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            response_model=ContentOutput,
        )
    except Exception as exc:
        _set_last_claude_error(f"Claude request failed: {str(exc)}")
        _set_last_content_pack(None)
        return None

    if not result.variants:
        _set_last_claude_error("Claude returned empty variants")
        _set_last_content_pack(None)
        return None

    variants: list[OutreachVariant] = []
    for item in result.variants[:2]:
        subject_line = item.subject_line.strip()
        hook = item.hook.strip()
        cta = item.cta.strip()
        hypothesis = item.hypothesis.strip()
        if not (subject_line and hook and cta):
            continue

        variants.append(
            OutreachVariant(
                subject_line=subject_line,
                hook=hook,
                cta=cta,
                hypothesis=hypothesis or "Outcome-aligned framing",
                provenance_chain=[],
            )
        )

    if not variants:
        _set_last_claude_error("Claude response did not contain valid subject/hook/cta fields")
        _set_last_content_pack(None)
        return None

    _set_last_claude_error(None)
    _set_last_content_pack(_content_pack_from_structured(result))
    return variants or None


async def _generate_variants_with_ollama(
    *,
    message: str,
    top_signals: list[SignalReference],
    learning_brief: str | None = None,
    preferred_angle: Literal["competitor_gap", "roi", "social_proof"] | None = None,
    product_name: str = "the product",
    persona_line: str = "You are a B2B growth expert.",
    style_hint: str = "cold-outreach email register, ROI/pipeline framing",
) -> list[OutreachVariant] | None:
    _set_last_ollama_error(None)
    config = _get_ollama_config()
    if config is None:
        _set_last_ollama_error("Ollama config missing (set OLLAMA_MODEL and optional OLLAMA_BASE_URL)")
        return None

    base_url, model = config

    signals_text = "\n".join([f"- [{s.source_type}] {s.raw_quote}" for s in top_signals])
    angle_a, angle_b = _preferred_variant_angles(preferred_angle)
    history_context = learning_brief or "No prior campaign winners available yet."
    prompt = f"""{persona_line} Write in {style_hint}.
Return ONLY valid JSON in this exact schema:
{{
  "variants": [
    {{"subject_line": "...", "hook": "...", "cta": "...", "hypothesis": "..."}},
    {{"subject_line": "...", "hook": "...", "cta": "...", "hypothesis": "..."}}
  ],
  "comparison_card_title": "...",
  "linkedin_posts": [
    {{"angle": "competitor_gap", "hook": "...", "hashtags": ["...", "..."]}},
    {{"angle": "roi_outcome", "hook": "...", "hashtags": ["...", "..."]}},
    {{"angle": "thought_leader", "hook": "...", "hashtags": ["...", "..."]}}
  ],
  "campaign_target_audience": "...",
  "campaign_next_actions": ["...", "...", "..."]
}}

Context signals:
{signals_text}

Historical performance memory:
{history_context}

Task:
- Generate 2 outreach email variants for {product_name} targeting the buyers most likely to purchase it.
- Variant A must lead with {_angle_prompt_name(angle_a)}.
- Variant B must lead with {_angle_prompt_name(angle_b)}.
- Keep each field concise and specific.
- If historical memory indicates a winning angle, bias your framing toward it unless current signals strongly contradict it.
- Also fill comparison_card_title, linkedin_posts, campaign_target_audience, campaign_next_actions, all grounded in {product_name}'s real category -- not generic sales/tech language.

User context: {message}
"""

    langchain_error: str | None = None
    llm = _get_ollama_chat_llm(base_url=base_url, model=model)
    if llm is not None and ChatPromptTemplate is not None:
        try:
            prompt_template = ChatPromptTemplate.from_messages([
                ("user", "{prompt_text}"),
            ])
            response = await llm.ainvoke(prompt_template.format_messages(prompt_text=prompt))
            raw_response = _extract_llm_content_text(response)
            if not raw_response:
                raise ValueError("ChatOllama returned an empty response")

            parsed = _loads_json_object(raw_response)
            structured = ContentOutput.model_validate(parsed)
            variants = _variants_from_structured_output(structured)
            if variants:
                _set_last_ollama_error(None)
                _set_last_content_pack(_content_pack_from_structured(structured))
                return variants

            raise ValueError("ChatOllama returned variants but subject/hook/cta fields were empty")
        except Exception as exc:
            langchain_error = f"ChatOllama request failed: {str(exc)}"

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.2},
    }

    try:
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            response = await client.post(f"{base_url}/api/generate", json=payload)
    except Exception as exc:
        message = f"Ollama request failed: {str(exc)}"
        if langchain_error:
            message = f"{langchain_error}; {message}"
        _set_last_ollama_error(message)
        return None

    if response.status_code >= 400:
        body_preview = response.text[:220].replace("\n", " ")
        message = f"Ollama HTTP {response.status_code}: {body_preview}"
        if langchain_error:
            message = f"{langchain_error}; {message}"
        _set_last_ollama_error(message)
        return None

    try:
        body = response.json()
    except Exception as exc:
        message = f"Ollama returned non-JSON response: {str(exc)}"
        if langchain_error:
            message = f"{langchain_error}; {message}"
        _set_last_ollama_error(message)
        return None

    if not isinstance(body, dict):
        message = "Ollama response body is not an object"
        if langchain_error:
            message = f"{langchain_error}; {message}"
        _set_last_ollama_error(message)
        return None

    raw_response = body.get("response")
    if not isinstance(raw_response, str) or not raw_response.strip():
        message = "Ollama response did not include a non-empty 'response' string"
        if langchain_error:
            message = f"{langchain_error}; {message}"
        _set_last_ollama_error(message)
        return None

    try:
        parsed = _loads_json_object(raw_response)
    except Exception as exc:
        message = f"Ollama response was not valid JSON: {str(exc)}"
        if langchain_error:
            message = f"{langchain_error}; {message}"
        _set_last_ollama_error(message)
        return None

    try:
        structured = ContentOutput.model_validate(parsed)
    except Exception as exc:
        message = f"Ollama JSON did not match schema: {str(exc)}"
        if langchain_error:
            message = f"{langchain_error}; {message}"
        _set_last_ollama_error(message)
        return None

    variants = _variants_from_structured_output(structured)

    if not variants:
        message = "Ollama returned variants but subject/hook/cta fields were empty"
        if langchain_error:
            message = f"{langchain_error}; {message}"
        _set_last_ollama_error(message)
        return None

    _set_last_ollama_error(None)
    _set_last_content_pack(_content_pack_from_structured(structured))
    return variants or None


async def _generate_variants_with_llm(
    *,
    message: str,
    top_signals: list[SignalReference],
    learning_brief: str | None = None,
    preferred_angle: Literal["competitor_gap", "roi", "social_proof"] | None = None,
    product_name: str = "the product",
    persona_line: str = "You are a B2B growth expert.",
    style_hint: str = "cold-outreach email register, ROI/pipeline framing",
) -> list[OutreachVariant] | None:
    _set_last_ollama_error(None)
    _set_last_claude_error(None)
    _set_last_content_pack(None)
    provider = _get_llm_provider()
    common_kwargs = {
        "message": message,
        "top_signals": top_signals,
        "learning_brief": learning_brief,
        "preferred_angle": preferred_angle,
        "product_name": product_name,
        "persona_line": persona_line,
        "style_hint": style_hint,
    }

    if provider == "ollama":
        variants = await _generate_variants_with_ollama(**common_kwargs)
        if variants:
            return variants
        return await _generate_variants_with_claude(**common_kwargs)

    if provider == "anthropic":
        variants = await _generate_variants_with_claude(**common_kwargs)
        if variants:
            return variants
        return await _generate_variants_with_ollama(**common_kwargs)

    # auto mode: prefer Anthropic if configured, then Ollama.
    variants = await _generate_variants_with_claude(**common_kwargs)
    if variants:
        return variants
    return await _generate_variants_with_ollama(**common_kwargs)


async def intent_router_node(state: dict[str, Any]) -> dict[str, Any]:
    state_model = coerce_state(state)
    current_stage = state_model.loop_stage
    message = state_model.message
    route_hint_raw = state.get("route_hint")

    _emit(NodeStartedEvent(type="node_started", node="intent_router", cycle_n=state_model.cycle_n))

    stage_map = {
        "research": "research",
        "generate": "generate",
        "ab": "ab",
        "outreach": "outreach",
        "feedback": "feedback",
    }

    forced_stage: str | None = None
    if isinstance(route_hint_raw, str) and route_hint_raw in stage_map.values():
        forced_stage = route_hint_raw

    if forced_stage:
        next_stage = forced_stage
    else:
        intent = detect_intent(message=message, current_stage=current_stage)
        next_stage = stage_map.get(intent, current_stage)

        # Guard intent routing when prerequisites are missing.
        if next_stage in {"generate", "ab", "outreach", "feedback"} and not state_model.signals:
            _emit(
                WarningEvent(
                    type="warning",
                    message="Intent requires prior signals; routing back to research.",
                    fallback_used=True,
                )
            )
            next_stage = "research"

        if next_stage in {"outreach", "feedback"} and not state_model.variants:
            _emit(
                WarningEvent(
                    type="warning",
                    message="Intent requires generated variants; routing back to research.",
                    fallback_used=True,
                )
            )
            next_stage = "research"

    try:
        next_stage = guarded_stage_transition(current_stage, next_stage)
    except ValueError:
        _emit(
            WarningEvent(
                type="warning",
                message=f"Invalid transition {current_stage} -> {next_stage}; preserving current stage.",
                fallback_used=True,
            )
        )
        next_stage = current_stage

    next_state = state_model.model_dump()
    next_state.update(
        {
            "loop_stage": next_stage,
            "route_hint": None,
        }
    )
    return next_state


def route_from_intent(state: dict[str, Any]) -> str:
    stage = str(state.get("loop_stage", "research"))
    route_map = {
        "research": ROUTE_LOOP_BACK,
        "generate": "content_generation",
        "ab": "ab_variant",
        "outreach": "outreach",
        "feedback": "feedback_ingestor",
    }
    return route_map.get(stage, ROUTE_LOOP_BACK)


async def _collect_channel_signals(thread_id: str) -> list[SignalReference]:
    """Channel & campaign intelligence: what's working where, derived from our
    own accumulated campaign_history rather than an external source -- this
    category is inherently about our own historical performance, not live
    market signal, so there's nothing to scrape and no paid call to make.
    """
    if not thread_id:
        return []

    history = await load_campaign_history(thread_id)
    if not history:
        return []

    by_channel: dict[str, list[CycleResult]] = {}
    for cycle in history:
        if cycle.channel:
            by_channel.setdefault(cycle.channel, []).append(cycle)

    if len(by_channel) < 2:
        return []

    averages = {
        channel: sum(c.reply_rate for c in cycles) / len(cycles) for channel, cycles in by_channel.items()
    }
    best_channel = max(averages, key=averages.get)
    worst_channel = min(averages, key=averages.get)
    if best_channel == worst_channel or averages[worst_channel] <= 0:
        return []

    lift = averages[best_channel] / averages[worst_channel]
    total_cycles = sum(len(cycles) for cycles in by_channel.values())
    confidence = min(0.85, 0.5 + 0.05 * total_cycles)

    content = (
        f"{best_channel} cycles average a {averages[best_channel] * 100:.1f}% reply rate "
        f"({lift:.1f}x {worst_channel}'s {averages[worst_channel] * 100:.1f}%) across "
        f"{len(by_channel[best_channel])} vs {len(by_channel[worst_channel])} cycles."
    )
    return [
        SignalReference(
            source_type="channel",
            source="internal_campaign_history",
            source_url=None,
            content=content,
            quote=content,
            confidence=confidence,
            raw_quote=content,
        )
    ]


async def market_intelligence_node(state: dict[str, Any]) -> dict[str, Any]:
    state_model = coerce_state(state)
    _emit(NodeStartedEvent(type="node_started", node="market_intelligence", cycle_n=state_model.cycle_n))

    message = state_model.message or "AI SDR market positioning"

    # Infer the real product/topic and its real competitors once per cycle, so
    # research isn't hardcoded to one product's competitive landscape
    # regardless of what's actually being asked. Claude first, live-search
    # fallback for the competitor half if that's unavailable/fails -- research
    # should never silently fall back to an unrelated domain list.
    inferred_name, discovered_domains, topic_analysis = await _infer_topic_context(message)
    if not discovered_domains:
        discovered_domains = await discover_competitor_domains_via_search(message)

    product_name = state_model.product_name
    if product_name == DEFAULT_PRODUCT_NAME and inferred_name:
        product_name = inferred_name
    elif product_name == DEFAULT_PRODUCT_NAME and not inferred_name:
        _emit(
            WarningEvent(
                type="warning",
                message="Could not infer the product name from this request; using the default demo product name. Set it explicitly in the Product Name field if this isn't intended.",
                fallback_used=True,
            )
        )

    product_category = topic_analysis.product_category if topic_analysis else state_model.product_category

    _emit(NodeStartedEvent(type="node_started", node="competitor_node", cycle_n=state_model.cycle_n))
    _emit(NodeStartedEvent(type="node_started", node="audience_node", cycle_n=state_model.cycle_n))
    _emit(NodeStartedEvent(type="node_started", node="pestel_node", cycle_n=state_model.cycle_n))
    _emit(NodeStartedEvent(type="node_started", node="adjacent_node_mcp", cycle_n=state_model.cycle_n))
    _emit(NodeStartedEvent(type="node_started", node="temporal_node_mcp", cycle_n=state_model.cycle_n))
    _emit(NodeStartedEvent(type="node_started", node="channel_node", cycle_n=state_model.cycle_n))

    async def _temporal_as_list(topic: str) -> list[SignalReference]:
        signal = await get_temporal_signal_via_mcp()
        return [signal] if signal else []

    results = await asyncio.gather(
        _collect_competitor_signals(message, discovered_domains),
        _collect_audience_signals(message, product_category),
        _collect_pestel_signals(message),
        scan_adjacent_via_mcp(message),
        _temporal_as_list(message),
        _collect_channel_signals(state_model.thread_id or ""),
        return_exceptions=True,
    )

    signals: list[SignalReference] = []
    source_order = ["competitor", "audience", "pestel", "adjacent", "temporal", "channel"]

    for idx, result in enumerate(results):
        if isinstance(result, Exception):
            source_name = source_order[idx]
            if source_name == "channel":
                # Not enough cross-channel history yet is normal, not a failure -- skip quietly.
                continue
            _emit(
                WarningEvent(
                    type="warning",
                    message=f"{source_name} signal source failed. Using fallback signals.",
                    fallback_used=True,
                )
            )
            continue
        signals.extend(result)

    if not any(signal.source_type == "competitor" for signal in signals):
        signals.extend(_fallback_competitor_signals(message))
        _emit(
            WarningEvent(
                type="warning",
                message="Competitor scraping returned no results for this topic; no competitor signal available this cycle.",
                fallback_used=True,
            )
        )

    if not any(signal.source_type == "audience" for signal in signals):
        signals.extend(_fallback_audience_signals(message))
        _emit(
            WarningEvent(
                type="warning",
                message="Audience scan returned no results for this topic; no audience signal available this cycle.",
                fallback_used=True,
            )
        )

    if not any(signal.source_type == "pestel" for signal in signals):
        signals.extend(_fallback_pestel_signals(message))
        pestel_reason = get_last_pestel_error()
        pestel_message = "PESTEL scan returned no results for this topic; no macro-trend signal available this cycle."
        if pestel_reason:
            pestel_message = f"{pestel_message} Details: {pestel_reason}"
        _emit(
            WarningEvent(
                type="warning",
                message=pestel_message,
                fallback_used=True,
            )
        )

    if not any(signal.source_type == "adjacent" for signal in signals):
        signals.extend(_fallback_adjacent_signals(message))
        _emit(
            WarningEvent(
                type="warning",
                message="Adjacent-threat scan returned no results for this topic; no adjacent-category signal available this cycle.",
                fallback_used=True,
            )
        )

    if not any(signal.source_type == "temporal" for signal in signals):
        signals.append(_fallback_temporal_signal())
        _emit(
            WarningEvent(
                type="warning",
                message="Temporal-context MCP tool returned no results; fallback signal used.",
                fallback_used=True,
            )
        )

    signals = _select_top_signals(signals, limit=12, query_context=message)

    for signal in signals:
        _emit(
            SignalFoundEvent(
                type="signal_found",
                source=signal.source_type,
                content=signal.content,
                confidence=signal.confidence,
                quote=signal.raw_quote,
            )
        )

    _emit(
        UIRenderEvent(
            type="ui_render",
            component=UIComponent.SIGNAL_BOARD,
            props={"signals": [_to_signal_card(s) for s in signals]},
            cycle_n=state_model.cycle_n,
        )
    )

    next_stage = guarded_stage_transition(state_model.loop_stage, "generate")

    next_state = state_model.model_dump()
    next_state.update(
        {
            "loop_stage": next_stage,
            "signals": [s.model_dump() for s in signals],
            "product_name": product_name,
            "product_category": product_category,
        }
    )
    return next_state


async def content_gen_node(state: dict[str, Any]) -> dict[str, Any]:
    state_model = coerce_state(state)
    _emit(NodeStartedEvent(type="node_started", node="content_gen", cycle_n=state_model.cycle_n))

    top_signals = _select_top_signals(state_model.signals, limit=5, query_context=state_model.message)
    preferred_angle = _infer_winning_angle(state_model.campaign_history)
    learning_brief = _build_learning_brief(state_model.campaign_history, preferred_angle)
    provider = _get_llm_provider()
    persona_line, style_hint = _persona_for_category(state_model.product_category)
    variants = await _generate_variants_with_llm(
        message=state_model.message,
        top_signals=top_signals,
        learning_brief=learning_brief,
        preferred_angle=preferred_angle,
        product_name=state_model.product_name,
        persona_line=persona_line,
        style_hint=style_hint,
    )
    content_pack = get_last_generated_content_pack()

    if not variants:
        variants = _fallback_variants(top_signals, preferred_angle=preferred_angle, product_name=state_model.product_name)
        llm_detail = _describe_llm_failure(provider)
        warning_message = "LLM generation unavailable or failed; deterministic fallback variants used."
        if preferred_angle:
            warning_message = (
                f"{warning_message} Historical bias applied: {_angle_prompt_name(preferred_angle)}."
            )
        if llm_detail:
            warning_message = f"{warning_message} Details: {llm_detail}"
        _emit(
            WarningEvent(
                type="warning",
                message=warning_message,
                fallback_used=True,
            )
        )

    next_stage = guarded_stage_transition(state_model.loop_stage, "ab")

    next_state = state_model.model_dump()
    next_state.update(
        {
            "variants": [variant.model_dump() for variant in variants],
            "loop_stage": next_stage,
            "content_pack": content_pack.model_dump() if content_pack else None,
        }
    )
    return next_state


def _build_comparison_card(
    signals: list[SignalReference],
    variants: list[OutreachVariant],
    product_name: str = "This product",
    content_pack: ContentPack | None = None,
) -> dict[str, Any]:
    """Build comparison card data from competitor signals and generated variants."""
    competitors: list[dict[str, Any]] = []

    # Our product — always first
    own_strengths: list[str] = []
    for variant in variants[:2]:
        if variant.hypothesis:
            own_strengths.append(variant.hypothesis[:120])
    if not own_strengths:
        own_strengths = ["Signal-driven outreach", "Full-loop campaign automation"]
    own_strengths = own_strengths[:3]

    competitors.append(
        {
            "name": product_name,
            "tagline": "Signal-driven growth with closed-loop learning",
            "strengths": own_strengths + ["Provenance-traced copy", "A/B hypothesis testing"],
            "weaknesses": ["Newer entrant in the market"],
            "highlight": True,
        }
    )

    # Extract competitor entries from signals
    seen_domains: set[str] = set()
    for signal in signals:
        if signal.source_type != "competitor":
            continue

        domain = signal.source.lower().strip()
        if domain in seen_domains:
            continue
        seen_domains.add(domain)

        display_name = domain.replace(".co", "").replace(".ai", "").replace(".com", "").title()
        tagline = signal.raw_quote[:100] if signal.raw_quote else "Competitor in this market"

        strengths: list[str] = []
        weaknesses: list[str] = []

        content_lower = (signal.content or "").lower()
        if "automat" in content_lower or "volume" in content_lower:
            strengths.append("High-volume automation")
            weaknesses.append("Limited reply quality optimization")
        if "person" in content_lower:
            strengths.append("Personalization features")
            weaknesses.append("Generic context insertion")
        if "email" in content_lower:
            strengths.append("Email campaign tooling")
            weaknesses.append("Limited multi-channel transparency")

        if not strengths:
            strengths = ["Established market presence", "Brand recognition"]
        if not weaknesses:
            weaknesses = ["Volume-over-quality approach", "No closed-loop learning"]

        competitors.append(
            {
                "name": display_name,
                "tagline": tagline[:100],
                "strengths": strengths[:3],
                "weaknesses": weaknesses[:3],
                "highlight": False,
            }
        )

    # Never pad with unrelated hardcoded companies -- if live discovery found
    # fewer real competitors, show fewer, and say so, rather than silently
    # presenting fabricated filler as real findings.
    real_competitor_count = len(competitors) - 1  # exclude our own product row
    if real_competitor_count < 3:
        _emit(
            WarningEvent(
                type="warning",
                message=(
                    f"Only {real_competitor_count} real competitor(s) found for this topic; "
                    "comparison card shows fewer entries than usual."
                ),
                fallback_used=True,
            )
        )

    # Summary insight from audience/PESTEL signals
    audience_insight = next(
        (s.raw_quote for s in signals if s.source_type in {"audience", "pestel"}),
        f"Limited live market signal available for {product_name} yet.",
    )

    title = (
        content_pack.comparison_card_title
        if content_pack and content_pack.comparison_card_title
        else f"{product_name} Competitive Landscape"
    )

    return {
        "title": title,
        "subtitle": "Live signal comparison — generated from real-time market data",
        "competitors": competitors[:4],
        "market_insight": audience_insight[:200],
    }


def _generic_hashtags_for_product(product_name: str, message: str) -> list[str]:
    """Build hashtags from the product's own name/topic instead of a fixed
    sales/tech vocabulary, so they're at least relevant to any category."""
    tokens: list[str] = []
    for word in re.findall(r"[A-Za-z0-9]+", f"{product_name} {message}"):
        if len(word) < 3 or word.lower() in {"the", "and", "for", "with", "this", "that"}:
            continue
        tag = f"#{word[0].upper()}{word[1:]}"
        if tag not in tokens:
            tokens.append(tag)
        if len(tokens) >= 3:
            break
    tokens.append("#MarketingStrategy")
    return tokens[:4]


def _build_linkedin_post_grid(
    signals: list[SignalReference],
    variants: list[OutreachVariant],
    message: str,
    product_name: str = "This product",
    content_pack: ContentPack | None = None,
) -> dict[str, Any]:
    def _best_signal_quote(source_type: str, fallback: str) -> str:
        for signal in signals:
            if signal.source_type != source_type:
                continue

            candidate = (signal.raw_quote or signal.quote or signal.content or "").strip()
            if candidate:
                return candidate
        return fallback

    competitor_quote = _best_signal_quote(
        "competitor",
        f"Limited live competitor signal available for {product_name} yet.",
    )
    audience_quote = _best_signal_quote(
        "audience",
        f"Limited live audience signal available for {product_name} yet.",
    )
    pestel_quote = _best_signal_quote(
        "pestel",
        f"Limited live market-trend signal available for {product_name} yet.",
    )

    lead_variant = variants[0] if variants else None
    secondary_variant = variants[1] if len(variants) > 1 else lead_variant
    default_hashtags = _generic_hashtags_for_product(product_name, message)
    packed_posts = {p.angle: p for p in (content_pack.linkedin_posts if content_pack else [])}

    def _copy_for(angle: str, fallback_hook: str) -> tuple[str, list[str]]:
        packed = packed_posts.get(angle)
        if packed and packed.hook:
            return packed.hook[:120], (packed.hashtags[:4] if packed.hashtags else default_hashtags)
        return fallback_hook[:120], default_hashtags

    competitor_gap_hook, competitor_gap_tags = _copy_for("competitor_gap", competitor_quote)
    roi_outcome_hook, roi_outcome_tags = _copy_for(
        "roi_outcome",
        lead_variant.subject_line if lead_variant else pestel_quote,
    )
    thought_leader_hook, thought_leader_tags = _copy_for("thought_leader", audience_quote)

    posts = [
        {
            "angle": "competitor_gap",
            "hook": competitor_gap_hook,
            "body": (
                f"Live market signal: \"{competitor_quote[:180]}\". "
                f"For {product_name}, the edge isn't more volume — it's tighter fit with what buyers actually respond to."
            ),
            "cta": "Comment and I’ll share how we’re thinking about this gap.",
            "hashtags": competitor_gap_tags,
        },
        {
            "angle": "roi_outcome",
            "hook": roi_outcome_hook,
            "body": (
                f"Signal-backed insight: \"{pestel_quote[:170]}\". "
                f"For teams we advise, this usually means focusing on one high-confidence hypothesis: "
                f"{(lead_variant.hypothesis if lead_variant else 'a results-led message')[:140]}."
            ),
            "cta": "Want the details behind this? Reply and I'll share.",
            "hashtags": roi_outcome_tags,
        },
        {
            "angle": "thought_leader",
            "hook": thought_leader_hook,
            "body": (
                f"Audience signal says: \"{audience_quote[:170]}\". "
                f"For {(message or product_name)[:90]}, winning teams ship fast experiments and double down on what converts."
            ),
            "cta": (
                f"If useful, I can share the exact experimentation loop we use. "
                f"({(secondary_variant.hypothesis if secondary_variant else 'Signal-driven positioning')[:90]})"
            ),
            "hashtags": thought_leader_tags,
        },
    ]

    return {
        "title": "LinkedIn Content Angles",
        "subtitle": "3 social-ready post drafts generated from live market signals",
        "posts": posts,
    }


def _build_campaign_brief(
    signals: list[SignalReference],
    variants: list[OutreachVariant],
    message: str,
    outreach_channel: str | None,
    product_name: str = "This product",
    content_pack: ContentPack | None = None,
) -> dict[str, Any]:
    audience_quote = next(
        (
            (s.raw_quote or s.quote or s.content or "").strip()
            for s in signals
            if s.source_type == "audience"
            and (s.raw_quote or s.quote or s.content)
        ),
        f"Limited live audience signal available for {product_name} yet.",
    )
    competitor_quotes = [
        (s.raw_quote or s.quote or s.content or "").strip()
        for s in signals
        if s.source_type == "competitor"
    ]
    top_competitor_gaps = [
        quote[:160]
        for quote in competitor_quotes[:2]
        if quote.strip()
    ]
    if not top_competitor_gaps:
        top_competitor_gaps = [f"Limited live competitor signal available for {product_name} yet."]

    key_messages: list[str] = []
    for variant in variants[:2]:
        if variant.hypothesis:
            key_messages.append(variant.hypothesis[:150])
    key_messages.append(audience_quote[:150])

    recommended_channels = ["LinkedIn", "Email"]
    if outreach_channel in {"LinkedIn", "Email", "Both"}:
        if outreach_channel == "Both":
            recommended_channels = ["LinkedIn", "Email"]
        else:
            recommended_channels = [outreach_channel, *(c for c in recommended_channels if c != outreach_channel)]

    target_audience = (
        content_pack.campaign_target_audience
        if content_pack and content_pack.campaign_target_audience
        else f"The buyers most likely to purchase {product_name}."
    )
    next_actions = (
        content_pack.campaign_next_actions
        if content_pack and content_pack.campaign_next_actions
        else [
            "Test two messaging variants with your target audience this week.",
            "Publish the top-performing angle on your primary channel and track engagement.",
            "Feed results back into the loop to refine the next cycle.",
        ]
    )

    return {
        "title": "Campaign Positioning Brief",
        "positioning_statement": (
            f"{product_name} helps its target audience act on real signal — competitor moves, "
            "audience demand, and market context — instead of guesswork, refined through continuous feedback."
        ),
        "target_audience": target_audience,
        "key_messages": key_messages[:3],
        "competitor_gaps": top_competitor_gaps,
        "recommended_channels": recommended_channels,
        "next_actions": next_actions,
        "context": message[:180],
    }


async def ab_variant_node(state: dict[str, Any]) -> dict[str, Any]:
    state_model = coerce_state(state)
    _emit(NodeStartedEvent(type="node_started", node="ab_variant", cycle_n=state_model.cycle_n))

    top_signals = _select_top_signals(state_model.signals, limit=5, query_context=state_model.message)
    preferred_angle = _infer_winning_angle(state_model.campaign_history)
    source_variants = state_model.variants or _fallback_variants(
        top_signals, preferred_angle=preferred_angle, product_name=state_model.product_name
    )
    variants = _enrich_variants(
        source_variants, top_signals, preferred_angle=preferred_angle, product_name=state_model.product_name
    )

    image_style = _image_style_for_category(state_model.product_category)
    openai_images = await asyncio.gather(
        *[
            generate_variant_image_data_uri(
                angle=_to_angle(variant.hypothesis),
                hook=variant.hook,
                product_name=state_model.product_name,
                style_suffix=image_style,
            )
            for variant in variants
        ],
        return_exceptions=True,
    )

    any_openai_used = False
    resolved_variants: list[OutreachVariant] = []
    for variant, openai_result in zip(variants, openai_images):
        image_url = openai_result if isinstance(openai_result, str) else None
        if image_url:
            any_openai_used = True
        else:
            image_url = generate_variant_image_url(
                angle=_to_angle(variant.hypothesis),
                hook=variant.hook,
                style_suffix=image_style,
            )
        resolved_variants.append(variant.model_copy(update={"image_url": image_url}))
    variants = resolved_variants

    if not any_openai_used:
        openai_reason = get_last_openai_image_error()
        warning_message = "OpenAI image generation unavailable; using free fallback image generator."
        if openai_reason:
            warning_message = f"{warning_message} Details: {openai_reason}"
        _emit(WarningEvent(type="warning", message=warning_message, fallback_used=True))

    variant_payload = [v.model_dump() for v in variants]

    _emit(
        UIRenderEvent(
            type="ui_render",
            component=UIComponent.AB_GRID,
            props={"variants": variant_payload},
            cycle_n=state_model.cycle_n,
        )
    )

    _emit(
        UIRenderEvent(
            type="ui_render",
            component=UIComponent.CHANNEL_PICKER,
            props={"selected": state_model.outreach_channel},
            cycle_n=state_model.cycle_n,
        )
    )

    # Emit a downloadable comparison card from competitor signals
    comparison_card = _build_comparison_card(
        state_model.signals, variants, state_model.product_name, state_model.content_pack
    )
    _emit(
        UIRenderEvent(
            type="ui_render",
            component=UIComponent.COMPARISON_CARD,
            props=comparison_card,
            cycle_n=state_model.cycle_n,
        )
    )

    linkedin_post_grid = _build_linkedin_post_grid(
        state_model.signals, variants, state_model.message, state_model.product_name, state_model.content_pack
    )
    _emit(
        UIRenderEvent(
            type="ui_render",
            component=UIComponent.LINKEDIN_POST_GRID,
            props=linkedin_post_grid,
            cycle_n=state_model.cycle_n,
        )
    )

    campaign_brief = _build_campaign_brief(
        state_model.signals,
        variants,
        state_model.message,
        state_model.outreach_channel,
        state_model.product_name,
        state_model.content_pack,
    )
    _emit(
        UIRenderEvent(
            type="ui_render",
            component=UIComponent.CAMPAIGN_BRIEF_CARD,
            props=campaign_brief,
            cycle_n=state_model.cycle_n,
        )
    )

    next_stage = guarded_stage_transition(state_model.loop_stage, "outreach")

    next_state = state_model.model_dump()
    next_state.update(
        {
            "variants": variant_payload,
            "loop_stage": next_stage,
        }
    )
    return next_state


def _zero_metrics(count: int) -> list[dict[str, Any]]:
    return [{"variant": i, "open_rate": 0.0, "reply_rate": 0.0, "click_rate": 0.0} for i in range(count)]


def reaction_counts_to_metrics(counts: list[int]) -> list[dict[str, Any]]:
    """Convert raw Discord reaction counts into the open/reply/click-rate shape
    the rest of the loop already understands. Reaction count is the only real
    signal Discord gives us here, so these three fields are derived from that
    single number rather than being three independent measurements:
      - reply_rate: each variant's share of total reactions (drives winner pick)
      - open_rate: raw engagement, normalized against a small demo-scale ceiling
      - click_rate: a damped composite of the two, kept mainly for the UI bars
    """
    total = sum(counts) or 1
    metrics: list[dict[str, Any]] = []
    for idx, count in enumerate(counts):
        share = count / total
        raw_engagement = min(count / 5, 1.0)
        metrics.append(
            {
                "variant": idx,
                "open_rate": round(raw_engagement, 3),
                "reply_rate": round(share, 3),
                "click_rate": round(raw_engagement * share, 3),
            }
        )
    return metrics


def _variant_post_content(variant: OutreachVariant, label: str) -> str:
    return (
        f"**{label}**\n"
        f"{variant.subject_line}\n\n"
        f"{variant.hook}\n\n"
        f"CTA: {variant.cta}\n\n"
        f"_React with any emoji to signal interest in this variant._"
    )


async def outreach_node(state: dict[str, Any]) -> dict[str, Any]:
    state_model = coerce_state(state)
    _emit(NodeStartedEvent(type="node_started", node="outreach", cycle_n=state_model.cycle_n))

    selected_channel = state_model.outreach_channel or "LinkedIn"
    selected_variant = state_model.selected_variant or (state_model.variants[0] if state_model.variants else None)

    if selected_channel in {"LinkedIn", "Both"}:
        _emit(
            UIRenderEvent(
                type="ui_render",
                component=UIComponent.LINKEDIN_POST_GRID,
                props=_build_linkedin_post_grid(
                    state_model.signals,
                    state_model.variants,
                    state_model.message,
                    state_model.product_name,
                    state_model.content_pack,
                ),
                cycle_n=state_model.cycle_n,
            )
        )

    # Sends (Discord post, real email) only fire on an explicit user click
    # (channel_select / deploy_variant sets outreach_requested=True for that
    # one run) -- never automatically as the graph loops through a new cycle.
    # This also keeps each channel independent: picking "LinkedIn" alone no
    # longer also fires the email send, and vice versa.
    should_post_discord = state_model.outreach_requested and selected_channel in {"LinkedIn", "Both"}
    should_send_email = state_model.outreach_requested and selected_channel in {"Email", "Both"}

    discord_message_ids: list[str] = state_model.discord_message_ids
    metrics: list[dict[str, Any]] = state_model.ab_results or _zero_metrics(min(2, len(state_model.variants)))
    if should_post_discord:
        try:
            new_discord_ids: list[str] = []
            for idx, variant in enumerate(state_model.variants[:2]):
                label = f"Variant {chr(65 + idx)} — Cycle {state_model.cycle_n}"
                posted = await post_variant_message(
                    label=label,
                    content=_variant_post_content(variant, label),
                    image_url=variant.image_url,
                )
                new_discord_ids.append(str(posted["id"]))
            discord_message_ids = new_discord_ids
            metrics = _zero_metrics(len(discord_message_ids))
        except DiscordNotConfigured:
            _emit(
                WarningEvent(
                    type="warning",
                    message="Discord channel not configured; using simulated engagement metrics.",
                    fallback_used=True,
                )
            )
            metrics = [
                {"variant": 0, "open_rate": 0.44, "reply_rate": 0.11, "click_rate": 0.08},
                {"variant": 1, "open_rate": 0.49, "reply_rate": 0.18, "click_rate": 0.1},
            ]
        except Exception as exc:
            _emit(
                WarningEvent(
                    type="warning",
                    message=f"Discord post failed ({str(exc)[:160]}); using simulated engagement metrics.",
                    fallback_used=True,
                )
            )
            metrics = [
                {"variant": 0, "open_rate": 0.44, "reply_rate": 0.11, "click_rate": 0.08},
                {"variant": 1, "open_rate": 0.49, "reply_rate": 0.18, "click_rate": 0.1},
            ]

    resend_email_ids: list[str] = state_model.resend_email_ids
    if should_send_email:
        try:
            # Capped at 2 variants per send (existing behavior) to stay well
            # under the provider's daily email quota -- sends now only happen
            # on an explicit click, never automatically, which is the other
            # half of using that quota conservatively.
            new_resend_ids: list[str] = []
            for idx, variant in enumerate(state_model.variants[:2]):
                label = f"Variant {chr(65 + idx)} — Cycle {state_model.cycle_n}"
                sent = await send_variant_email(
                    label=label,
                    subject_line=variant.subject_line,
                    hook=variant.hook,
                    cta=variant.cta,
                    image_url=variant.image_url,
                )
                new_resend_ids.append(str(sent["id"]))
            resend_email_ids = new_resend_ids
        except ResendNotConfigured:
            _emit(
                WarningEvent(
                    type="warning",
                    message="Email channel not configured (RESEND_API_KEY/RESEND_TEST_RECIPIENT missing); skipping real send.",
                    fallback_used=True,
                )
            )
        except Exception as exc:
            _emit(
                WarningEvent(
                    type="warning",
                    message=f"Email send failed ({str(exc)[:160]}).",
                    fallback_used=True,
                )
            )

    thread_id = state_model.thread_id or "local-thread"
    await save_ab_results(
        thread_id=thread_id,
        cycle_n=state_model.cycle_n,
        variants=state_model.variants,
        metrics=metrics,
        discord_message_ids=discord_message_ids,
    )

    _emit(
        UIRenderEvent(
            type="ui_render",
            component=UIComponent.FEEDBACK_PANEL,
            props={
                "metrics": metrics,
                "selected_channel": selected_channel,
                "campaign_history": [entry.model_dump() for entry in state_model.campaign_history],
                "discord_message_ids": discord_message_ids,
                "resend_email_ids": resend_email_ids,
            },
            cycle_n=state_model.cycle_n,
        )
    )

    next_stage = guarded_stage_transition(state_model.loop_stage, "feedback")

    next_state = state_model.model_dump()
    next_state.update(
        {
            "selected_variant": selected_variant.model_dump() if selected_variant else None,
            "ab_results": metrics,
            "outreach_channel": selected_channel,
            "loop_stage": next_stage,
            "discord_message_ids": discord_message_ids,
            "resend_email_ids": resend_email_ids,
            # Always reset: outreach_requested must be re-set explicitly by
            # the next channel_select/deploy_variant click, not inherited by
            # a later automatic cycle transition.
            "outreach_requested": False,
        }
    )
    return next_state


def _pick_winner_variant(variants: list[OutreachVariant], metrics: list[dict[str, Any]]) -> OutreachVariant | None:
    if not variants:
        return None

    if not metrics:
        return variants[0]

    winner_metric = max(metrics, key=lambda m: float(m.get("reply_rate", 0)))
    winner_index = int(winner_metric.get("variant", 0))
    if 0 <= winner_index < len(variants):
        return variants[winner_index]
    return variants[0]


async def feedback_ingestor_node(state: dict[str, Any]) -> dict[str, Any]:
    state_model = coerce_state(state)
    _emit(NodeStartedEvent(type="node_started", node="feedback_ingestor", cycle_n=state_model.cycle_n))

    feedback_events = state_model.feedback_events
    campaign_history = list(state_model.campaign_history)
    thread_id = state_model.thread_id or ""

    persisted_metrics = await load_ab_results(thread_id=thread_id, cycle_n=state_model.cycle_n) if thread_id else None
    effective_metrics = persisted_metrics or state_model.ab_results
    winner_variant = _pick_winner_variant(state_model.variants, effective_metrics)

    if feedback_events:
        feedback = feedback_events[-1]
        # Scoped to the variant that actually won THIS cycle, not the
        # highest-confidence signal ever seen across the whole thread --
        # otherwise an early high-confidence signal keeps "winning" here
        # forever, showing the same sentence even when a different variant
        # wins in a later cycle.
        if winner_variant and winner_variant.provenance_chain:
            top_signal = max(winner_variant.provenance_chain, key=lambda s: s.confidence).content
        elif state_model.signals:
            top_signal = max(state_model.signals, key=lambda s: s.confidence).content
        else:
            top_signal = "No top signal"
        winner_metric = max(effective_metrics, key=lambda m: float(m.get("reply_rate", 0)), default={})

        cycle_result = CycleResult(
            cycle_n=state_model.cycle_n + 1,
            top_signal=top_signal,
            winning_variant=(
                feedback.winning_variant
                or (winner_variant.subject_line if winner_variant else "Variant A")
            ),
            open_rate=float(feedback.open_rate or winner_metric.get("open_rate", 0.0)),
            reply_rate=float(feedback.reply_rate or winner_metric.get("reply_rate", 0.0)),
            angle=feedback.angle or _to_angle((winner_variant.hypothesis if winner_variant else "competitor_gap")),
            channel=feedback.channel or state_model.outreach_channel,
        )
        campaign_history.append(cycle_result)
        await save_campaign_history(thread_id=state_model.thread_id or "local-thread", cycle_result=cycle_result)

        completed_cycle_n = state_model.cycle_n
        next_cycle_n = state_model.cycle_n + 1
        next_stage = "research"
        next_action: Literal["awaiting_feedback", "refined_research", "end"] = "refined_research"
        feedback_event_update: list[dict[str, Any]] = []
    else:
        completed_cycle_n = state_model.cycle_n
        next_cycle_n = state_model.cycle_n
        next_stage = "feedback"
        next_action = "awaiting_feedback"
        feedback_event_update = []

    # Emit feedback panel updates only when explicit feedback has been ingested.
    # The outreach node already renders the initial metrics panel for the cycle.
    if feedback_events:
        _emit(
            UIRenderEvent(
                type="ui_render",
                component=UIComponent.FEEDBACK_PANEL,
                props={
                    "metrics": effective_metrics,
                    "campaign_history": [entry.model_dump() for entry in campaign_history],
                },
                cycle_n=state_model.cycle_n,
            )
        )

    _emit(
        LoopCompleteEvent(
            type="loop_complete",
            cycle_n=completed_cycle_n,
            next_action=next_action,
        )
    )

    next_state = state_model.model_dump()
    next_state.update(
        {
            "campaign_history": [entry.model_dump() for entry in campaign_history],
            "ab_results": effective_metrics,
            "cycle_n": next_cycle_n,
            "feedback_events": feedback_event_update,
            "loop_stage": next_stage,
        }
    )
    return next_state


def route_after_feedback(state: dict[str, Any]) -> str:
    # Loop continuation is controlled by loop_stage after feedback processing.
    if state.get("loop_stage") == "research":
        return ROUTE_LOOP_BACK
    return ROUTE_END
