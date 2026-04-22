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

from constants import ROUTE_END, ROUTE_LOOP_BACK, UIComponent
from events import LoopCompleteEvent, NodeStartedEvent, SignalFoundEvent, UIRenderEvent, WarningEvent
from geo_context import detect_geo_context, get_geo_terms
from intent_router import detect_intent
from mcp_tools import TARGETS, get_last_pestel_error, scan_audience_intent, scan_pestel_trends, scrape_competitor
from persistence import load_ab_results, load_signal_cache, save_ab_results, save_signal_cache
from state import CycleResult, OutreachVariant, SignalReference, coerce_state, guarded_stage_transition


class GeneratedVariant(BaseModel):
    subject_line: str
    hook: str
    cta: str
    hypothesis: str


class ContentOutput(BaseModel):
    variants: list[GeneratedVariant] = Field(default_factory=list)


_anthropic_client = None
_anthropic_initialized = False
_last_ollama_error: str | None = None
_last_claude_error: str | None = None
_ollama_chat_llm = None
_ollama_chat_llm_config: tuple[str, str] | None = None


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
    }
    return base_scores.get(signal.source_type, 0.65)


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
    for source_type in ("competitor", "audience", "pestel"):
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
    clipped_message = (message or "AI SDR market")[:120]
    return [
        SignalReference(
            source_type="competitor",
            source="artisan.co",
            source_url="https://artisan.co",
            content=f"Competitor positioning hint from prompt: {clipped_message}",
            quote="Competitors emphasize high-volume outbound; weak objection handling depth.",
            confidence=0.82,
            raw_quote="Competitors emphasize high-volume outbound; weak objection handling depth.",
        ),
        SignalReference(
            source_type="competitor",
            source="11x.ai",
            source_url="https://11x.ai",
            content="Strong email automation claims but limited cross-channel transparency.",
            quote="Strong email automation claims but limited cross-channel transparency.",
            confidence=0.78,
            raw_quote="Strong email automation claims but limited cross-channel transparency.",
        ),
    ]


def _fallback_pestel_signals(message: str = "") -> list[SignalReference]:
    geo = detect_geo_context(message)
    if geo is not None:
        signal_text = (
            f"{geo.country_name} GTM teams are cost-sensitive and increasingly prioritize measurable "
            "pipeline impact over send-volume metrics."
        )
    else:
        signal_text = "AI SDR market interest remains elevated with clear demand for measurable pipeline outcomes."

    return [
        SignalReference(
            source_type="pestel",
            source="google_trends",
            source_url="https://trends.google.com/",
            content=signal_text,
            quote=signal_text,
            confidence=0.71,
            raw_quote=signal_text,
        )
    ]


def _fallback_audience_signals(message: str = "") -> list[SignalReference]:
    geo = detect_geo_context(message)
    if geo is not None:
        signal_text = (
            f"{geo.country_name} B2B sellers ask for practical, budget-aware personalization "
            "that improves reply quality."
        )
    else:
        signal_text = "Leaders are tired of generic personalization and fake context."

    return [
        SignalReference(
            source_type="audience",
            source="reddit/r/sales",
            source_url="https://reddit.com/r/sales",
            content=signal_text,
            quote=signal_text,
            confidence=0.87,
            raw_quote=signal_text,
        )
    ]


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


def _competitor_targets_for_topic(topic: str) -> list[str]:
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

    return list(TARGETS)


def _fallback_variant_for_angle(
    angle: Literal["competitor_gap", "roi", "social_proof"],
    *,
    competitor_quote: str,
    outcome_quote: str,
) -> OutreachVariant:
    if angle == "roi":
        return OutreachVariant(
            subject_line="A practical path to 3x better AI SDR reply rates",
            hook=f"Revenue teams now care most about outcomes and attribution — {outcome_quote[:140]}",
            cta="Want the ROI playbook we use with Series B sales teams?",
            hypothesis="ROI framing should win with VP Sales buyers focused on predictable pipeline.",
            provenance_chain=[],
        )

    if angle == "social_proof":
        return OutreachVariant(
            subject_line="How peer teams are improving reply rates with AI SDRs",
            hook=f"Top teams respond faster to concrete proof over claims — {outcome_quote[:140]}",
            cta="Want 3 real examples we can adapt to your outreach this week?",
            hypothesis="Social proof framing should reduce skepticism by showing credible peer outcomes.",
            provenance_chain=[],
        )

    return OutreachVariant(
        subject_line="The AI SDR gap most teams are still paying for",
        hook=f"Most AI SDR tools optimize sends, not conversions — {competitor_quote[:140]}",
        cta="Open to a 15-minute gap analysis this week?",
        hypothesis="Competitor gap framing will create urgency by naming an avoidable risk.",
        provenance_chain=[],
    )


def _fallback_variants(
    top_signals: list[SignalReference],
    *,
    preferred_angle: Literal["competitor_gap", "roi", "social_proof"] | None = None,
) -> list[OutreachVariant]:
    competitor_quote = next((s.raw_quote for s in top_signals if s.source_type == "competitor"), "AI SDR tools over-index on volume")
    outcome_quote = next(
        (s.raw_quote for s in top_signals if s.source_type in {"audience", "pestel"}),
        "Teams are prioritizing measurable pipeline outcomes",
    )

    first_angle, second_angle = _preferred_variant_angles(preferred_angle)

    return [
        _fallback_variant_for_angle(first_angle, competitor_quote=competitor_quote, outcome_quote=outcome_quote),
        _fallback_variant_for_angle(second_angle, competitor_quote=competitor_quote, outcome_quote=outcome_quote),
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

    fallback_pool = _fallback_variants(top_signals, preferred_angle=preferred_angle)
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


async def _collect_competitor_signals(topic: str) -> list[SignalReference]:
    signals: list[SignalReference] = []
    for domain in _competitor_targets_for_topic(topic):
        cached = await load_signal_cache(domain=domain, topic=topic)
        if cached:
            signals.extend(cached)
            continue

        scraped = await scrape_competitor(domain)
        if scraped:
            signals.extend(scraped)
            await save_signal_cache(domain=domain, topic=topic, signals=scraped)
    return signals


async def _collect_audience_signals(topic: str) -> list[SignalReference]:
    cache_key = "reddit_audience"
    cached = await load_signal_cache(domain=cache_key, topic=topic)
    if cached:
        return cached

    scanned = await scan_audience_intent(topic)
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
) -> list[OutreachVariant] | None:
    _set_last_claude_error(None)
    client = _get_anthropic_client()
    if client is None:
        _set_last_claude_error("Anthropic client unavailable (missing/invalid ANTHROPIC_API_KEY or dependency)")
        return None

    signals_text = "\n".join([f"- [{s.source_type}] {s.raw_quote}" for s in top_signals])
    angle_a, angle_b = _preferred_variant_angles(preferred_angle)
    history_context = learning_brief or "No prior campaign winners available yet."

    prompt = f"""You are a B2B growth expert. Based on these live market signals about the AI SDR space:

{signals_text}

Historical performance memory:
{history_context}

Generate 2 outreach email variants for Lilian (Vector Agents AI SDR) targeting VP Sales at Series B companies.

Variant A: Lead with {_angle_prompt_name(angle_a)}
Variant B: Lead with {_angle_prompt_name(angle_b)}

If historical memory indicates a winning angle, bias your framing toward it unless current signals strongly contradict it.

Each variant must include: subject_line, hook (first sentence), cta, hypothesis.
Keep each field concise and specific.
User context: {message}
"""

    try:
        result = await client.messages.create(
            model="claude-sonnet-4-5",
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
        return None

    if not result.variants:
        _set_last_claude_error("Claude returned empty variants")
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
        return None

    _set_last_claude_error(None)
    return variants or None


async def _generate_variants_with_ollama(
    *,
    message: str,
    top_signals: list[SignalReference],
    learning_brief: str | None = None,
    preferred_angle: Literal["competitor_gap", "roi", "social_proof"] | None = None,
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
    prompt = f"""You are a B2B growth expert.
Return ONLY valid JSON in this exact schema:
{{
  "variants": [
    {{"subject_line": "...", "hook": "...", "cta": "...", "hypothesis": "..."}},
    {{"subject_line": "...", "hook": "...", "cta": "...", "hypothesis": "..."}}
  ]
}}

Context signals:
{signals_text}

Historical performance memory:
{history_context}

Task:
- Generate 2 outreach email variants for Lilian (Vector Agents AI SDR) targeting VP Sales at Series B companies.
- Variant A must lead with {_angle_prompt_name(angle_a)}.
- Variant B must lead with {_angle_prompt_name(angle_b)}.
- Keep each field concise and specific.
- If historical memory indicates a winning angle, bias your framing toward it unless current signals strongly contradict it.

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
    return variants or None


async def _generate_variants_with_llm(
    *,
    message: str,
    top_signals: list[SignalReference],
    learning_brief: str | None = None,
    preferred_angle: Literal["competitor_gap", "roi", "social_proof"] | None = None,
) -> list[OutreachVariant] | None:
    _set_last_ollama_error(None)
    _set_last_claude_error(None)
    provider = _get_llm_provider()

    if provider == "ollama":
        variants = await _generate_variants_with_ollama(
            message=message,
            top_signals=top_signals,
            learning_brief=learning_brief,
            preferred_angle=preferred_angle,
        )
        if variants:
            return variants
        return await _generate_variants_with_claude(
            message=message,
            top_signals=top_signals,
            learning_brief=learning_brief,
            preferred_angle=preferred_angle,
        )

    if provider == "anthropic":
        variants = await _generate_variants_with_claude(
            message=message,
            top_signals=top_signals,
            learning_brief=learning_brief,
            preferred_angle=preferred_angle,
        )
        if variants:
            return variants
        return await _generate_variants_with_ollama(
            message=message,
            top_signals=top_signals,
            learning_brief=learning_brief,
            preferred_angle=preferred_angle,
        )

    # auto mode: prefer Anthropic if configured, then Ollama.
    variants = await _generate_variants_with_claude(
        message=message,
        top_signals=top_signals,
        learning_brief=learning_brief,
        preferred_angle=preferred_angle,
    )
    if variants:
        return variants
    return await _generate_variants_with_ollama(
        message=message,
        top_signals=top_signals,
        learning_brief=learning_brief,
        preferred_angle=preferred_angle,
    )


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


async def market_intelligence_node(state: dict[str, Any]) -> dict[str, Any]:
    state_model = coerce_state(state)
    _emit(NodeStartedEvent(type="node_started", node="market_intelligence", cycle_n=state_model.cycle_n))

    message = state_model.message or "AI SDR market positioning"

    _emit(NodeStartedEvent(type="node_started", node="competitor_node", cycle_n=state_model.cycle_n))
    _emit(NodeStartedEvent(type="node_started", node="audience_node", cycle_n=state_model.cycle_n))
    _emit(NodeStartedEvent(type="node_started", node="pestel_node", cycle_n=state_model.cycle_n))

    results = await asyncio.gather(
        _collect_competitor_signals(message),
        _collect_audience_signals(message),
        _collect_pestel_signals(message),
        return_exceptions=True,
    )

    signals: list[SignalReference] = []

    for idx, result in enumerate(results):
        if isinstance(result, Exception):
            source_name = ["competitor", "audience", "pestel"][idx]
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
                message="Competitor scraping returned no results; fallback competitor signals used.",
                fallback_used=True,
            )
        )

    if not any(signal.source_type == "audience" for signal in signals):
        signals.extend(_fallback_audience_signals(message))
        _emit(
            WarningEvent(
                type="warning",
                message="Audience scan returned no results; fallback audience signals used.",
                fallback_used=True,
            )
        )

    if not any(signal.source_type == "pestel" for signal in signals):
        signals.extend(_fallback_pestel_signals(message))
        pestel_reason = get_last_pestel_error()
        pestel_message = "PESTEL scan returned no results; fallback macro signals used."
        if pestel_reason:
            pestel_message = f"{pestel_message} Details: {pestel_reason}"
        _emit(
            WarningEvent(
                type="warning",
                message=pestel_message,
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
    variants = await _generate_variants_with_llm(
        message=state_model.message,
        top_signals=top_signals,
        learning_brief=learning_brief,
        preferred_angle=preferred_angle,
    )

    if not variants:
        variants = _fallback_variants(top_signals, preferred_angle=preferred_angle)
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
        }
    )
    return next_state


def _build_comparison_card(
    signals: list[SignalReference],
    variants: list[OutreachVariant],
) -> dict[str, Any]:
    """Build comparison card data from competitor signals and generated variants."""
    competitors: list[dict[str, Any]] = []

    # Lilian (our product) — always first
    lilian_strengths: list[str] = []
    for variant in variants[:2]:
        if variant.hypothesis:
            lilian_strengths.append(variant.hypothesis[:120])
    if not lilian_strengths:
        lilian_strengths = ["Signal-driven outreach", "Full-loop campaign automation"]
    lilian_strengths = lilian_strengths[:3]

    competitors.append(
        {
            "name": "Lilian (Vector Agents)",
            "tagline": "Signal-driven AI SDR with closed-loop learning",
            "strengths": lilian_strengths + ["Provenance-traced copy", "A/B hypothesis testing"],
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
        tagline = signal.raw_quote[:100] if signal.raw_quote else "AI-powered SDR platform"

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

    # Ensure at least 3 entries for a meaningful comparison
    defaults = [
        {
            "name": "Artisan",
            "tagline": "Autonomous AI BDR — Hire Ava",
            "strengths": ["All-in-one platform", "Autonomous prospecting"],
            "weaknesses": ["Volume-first approach", "Limited signal transparency"],
            "highlight": False,
        },
        {
            "name": "11x",
            "tagline": "AI workers that scale your go-to-market",
            "strengths": ["Strong email automation", "Enterprise positioning"],
            "weaknesses": ["Limited cross-channel transparency", "No closed-loop feedback"],
            "highlight": False,
        },
    ]
    existing_names = {c["name"].lower() for c in competitors}
    for default in defaults:
        if default["name"].lower() not in existing_names and len(competitors) < 4:
            competitors.append(default)

    # Summary insight from audience/PESTEL signals
    audience_insight = next(
        (s.raw_quote for s in signals if s.source_type in {"audience", "pestel"}),
        "B2B teams prioritize measurable pipeline outcomes over send-volume metrics.",
    )

    return {
        "title": "AI SDR Competitive Landscape",
        "subtitle": "Live signal comparison — generated from real-time market data",
        "competitors": competitors[:4],
        "market_insight": audience_insight[:200],
    }


async def ab_variant_node(state: dict[str, Any]) -> dict[str, Any]:
    state_model = coerce_state(state)
    _emit(NodeStartedEvent(type="node_started", node="ab_variant", cycle_n=state_model.cycle_n))

    top_signals = _select_top_signals(state_model.signals, limit=5, query_context=state_model.message)
    preferred_angle = _infer_winning_angle(state_model.campaign_history)
    source_variants = state_model.variants or _fallback_variants(top_signals, preferred_angle=preferred_angle)
    variants = _enrich_variants(source_variants, top_signals, preferred_angle=preferred_angle)

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
    comparison_card = _build_comparison_card(state_model.signals, variants)
    _emit(
        UIRenderEvent(
            type="ui_render",
            component=UIComponent.COMPARISON_CARD,
            props=comparison_card,
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


async def outreach_node(state: dict[str, Any]) -> dict[str, Any]:
    state_model = coerce_state(state)
    _emit(NodeStartedEvent(type="node_started", node="outreach", cycle_n=state_model.cycle_n))

    selected_channel = state_model.outreach_channel or "LinkedIn"
    selected_variant = state_model.selected_variant or (state_model.variants[0] if state_model.variants else None)

    metrics = [
        {"variant": 0, "open_rate": 0.44, "reply_rate": 0.11, "click_rate": 0.08},
        {"variant": 1, "open_rate": 0.49, "reply_rate": 0.18, "click_rate": 0.1},
    ]

    thread_id = state_model.thread_id or "local-thread"
    await save_ab_results(
        thread_id=thread_id,
        cycle_n=state_model.cycle_n,
        variants=state_model.variants,
        metrics=metrics,
    )

    _emit(
        UIRenderEvent(
            type="ui_render",
            component=UIComponent.FEEDBACK_PANEL,
            props={
                "metrics": metrics,
                "selected_channel": selected_channel,
                "campaign_history": [entry.model_dump() for entry in state_model.campaign_history],
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
        top_signal = max(state_model.signals, key=lambda s: s.confidence).content if state_model.signals else "No top signal"
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
        )
        campaign_history.append(cycle_result)

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
