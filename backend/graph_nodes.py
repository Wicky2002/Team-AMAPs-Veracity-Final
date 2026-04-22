from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Literal

import httpx
from langgraph.config import get_stream_writer
from pydantic import BaseModel, Field

try:
    import anthropic
    import instructor
except Exception:  # pragma: no cover - optional dependency guard
    anthropic = None
    instructor = None

from events import LoopCompleteEvent, NodeStartedEvent, SignalFoundEvent, UIRenderEvent, WarningEvent
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


def _copy_signal(signal: SignalReference) -> SignalReference:
    return SignalReference.model_validate(signal.model_dump())


def _select_top_signals(signals: list[SignalReference], limit: int = 5) -> list[SignalReference]:
    return sorted(signals, key=lambda sig: sig.confidence, reverse=True)[:limit]


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


def _fallback_pestel_signals() -> list[SignalReference]:
    return [
        SignalReference(
            source_type="pestel",
            source="google_trends",
            source_url="https://trends.google.com/",
            content="AI SDR market interest remains elevated with clear demand for measurable pipeline outcomes.",
            quote="AI SDR market interest remains elevated with clear demand for measurable pipeline outcomes.",
            confidence=0.71,
            raw_quote="AI SDR market interest remains elevated with clear demand for measurable pipeline outcomes.",
        )
    ]


def _fallback_audience_signals() -> list[SignalReference]:
    return [
        SignalReference(
            source_type="audience",
            source="reddit/r/sales",
            source_url="https://reddit.com/r/sales",
            content="Leaders are tired of generic personalization and fake context.",
            quote="Leaders are tired of generic personalization and fake context.",
            confidence=0.87,
            raw_quote="Leaders are tired of generic personalization and fake context.",
        )
    ]


def _fallback_variants(top_signals: list[SignalReference]) -> list[OutreachVariant]:
    competitor_quote = next((s.raw_quote for s in top_signals if s.source_type == "competitor"), "AI SDR tools over-index on volume")
    outcome_quote = next(
        (s.raw_quote for s in top_signals if s.source_type in {"audience", "pestel"}),
        "Teams are prioritizing measurable pipeline outcomes",
    )

    return [
        OutreachVariant(
            subject_line="The AI SDR gap most teams are still paying for",
            hook=f"Most AI SDR tools optimize sends, not conversions — {competitor_quote[:140]}",
            cta="Open to a 15-minute gap analysis this week?",
            hypothesis="Competitor gap framing will create urgency by naming an avoidable risk.",
            provenance_chain=[],
        ),
        OutreachVariant(
            subject_line="A practical path to 3x better AI SDR reply rates",
            hook=f"Revenue teams now care most about outcomes and attribution — {outcome_quote[:140]}",
            cta="Want the ROI playbook we use with Series B sales teams?",
            hypothesis="ROI framing should win with VP Sales buyers focused on predictable pipeline.",
            provenance_chain=[],
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


def _enrich_variants(variants: list[OutreachVariant], top_signals: list[SignalReference]) -> list[OutreachVariant]:
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

    while len(enriched) < 2:
        fallback_variant = _fallback_variants(top_signals)[len(enriched)]
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
    for domain in TARGETS:
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
) -> list[OutreachVariant] | None:
    _set_last_claude_error(None)
    client = _get_anthropic_client()
    if client is None:
        _set_last_claude_error("Anthropic client unavailable (missing/invalid ANTHROPIC_API_KEY or dependency)")
        return None

    signals_text = "\n".join([f"- [{s.source_type}] {s.raw_quote}" for s in top_signals])

    prompt = f"""You are a B2B growth expert. Based on these live market signals about the AI SDR space:

{signals_text}

Generate 2 outreach email variants for Lilian (Vector Agents AI SDR) targeting VP Sales at Series B companies.

Variant A: Lead with competitor gap angle
Variant B: Lead with ROI/outcome angle

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
) -> list[OutreachVariant] | None:
    _set_last_ollama_error(None)
    config = _get_ollama_config()
    if config is None:
        _set_last_ollama_error("Ollama config missing (set OLLAMA_MODEL and optional OLLAMA_BASE_URL)")
        return None

    base_url, model = config

    signals_text = "\n".join([f"- [{s.source_type}] {s.raw_quote}" for s in top_signals])
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

Task:
- Generate 2 outreach email variants for Lilian (Vector Agents AI SDR) targeting VP Sales at Series B companies.
- Variant A must lead with competitor gap angle.
- Variant B must lead with ROI/outcome angle.
- Keep each field concise and specific.

User context: {message}
"""

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
        _set_last_ollama_error(f"Ollama request failed: {str(exc)}")
        return None

    if response.status_code >= 400:
        body_preview = response.text[:220].replace("\n", " ")
        _set_last_ollama_error(f"Ollama HTTP {response.status_code}: {body_preview}")
        return None

    try:
        body = response.json()
    except Exception as exc:
        _set_last_ollama_error(f"Ollama returned non-JSON response: {str(exc)}")
        return None

    if not isinstance(body, dict):
        _set_last_ollama_error("Ollama response body is not an object")
        return None

    raw_response = body.get("response")
    if not isinstance(raw_response, str) or not raw_response.strip():
        _set_last_ollama_error("Ollama response did not include a non-empty 'response' string")
        return None

    try:
        parsed = json.loads(raw_response)
    except Exception as exc:
        _set_last_ollama_error(f"Ollama response was not valid JSON: {str(exc)}")
        return None

    try:
        structured = ContentOutput.model_validate(parsed)
    except Exception as exc:
        _set_last_ollama_error(f"Ollama JSON did not match schema: {str(exc)}")
        return None

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

    if not variants:
        _set_last_ollama_error("Ollama returned variants but subject/hook/cta fields were empty")
        return None

    _set_last_ollama_error(None)
    return variants or None


async def _generate_variants_with_llm(
    *,
    message: str,
    top_signals: list[SignalReference],
) -> list[OutreachVariant] | None:
    _set_last_ollama_error(None)
    _set_last_claude_error(None)
    provider = _get_llm_provider()

    if provider == "ollama":
        variants = await _generate_variants_with_ollama(message=message, top_signals=top_signals)
        if variants:
            return variants
        return await _generate_variants_with_claude(message=message, top_signals=top_signals)

    if provider == "anthropic":
        variants = await _generate_variants_with_claude(message=message, top_signals=top_signals)
        if variants:
            return variants
        return await _generate_variants_with_ollama(message=message, top_signals=top_signals)

    # auto mode: prefer Anthropic if configured, then Ollama.
    variants = await _generate_variants_with_claude(message=message, top_signals=top_signals)
    if variants:
        return variants
    return await _generate_variants_with_ollama(message=message, top_signals=top_signals)


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
        "research": "market_intelligence",
        "generate": "content_generation",
        "ab": "ab_variant",
        "outreach": "outreach",
        "feedback": "feedback_ingestor",
    }
    return route_map.get(stage, "market_intelligence")


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
        signals.extend(_fallback_audience_signals())
        _emit(
            WarningEvent(
                type="warning",
                message="Audience scan returned no results; fallback audience signals used.",
                fallback_used=True,
            )
        )

    if not any(signal.source_type == "pestel" for signal in signals):
        signals.extend(_fallback_pestel_signals())
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

    signals = _select_top_signals(signals, limit=12)

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
            component="SignalIntelligenceBoard",
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

    top_signals = _select_top_signals(state_model.signals, limit=5)
    provider = _get_llm_provider()
    variants = await _generate_variants_with_llm(
        message=state_model.message,
        top_signals=top_signals,
    )

    if not variants:
        variants = _fallback_variants(top_signals)
        llm_detail = _describe_llm_failure(provider)
        warning_message = "LLM generation unavailable or failed; deterministic fallback variants used."
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


async def ab_variant_node(state: dict[str, Any]) -> dict[str, Any]:
    state_model = coerce_state(state)
    _emit(NodeStartedEvent(type="node_started", node="ab_variant", cycle_n=state_model.cycle_n))

    top_signals = _select_top_signals(state_model.signals, limit=5)
    source_variants = state_model.variants or _fallback_variants(top_signals)
    variants = _enrich_variants(source_variants, top_signals)

    variant_payload = [v.model_dump() for v in variants]

    _emit(
        UIRenderEvent(
            type="ui_render",
            component="ABVariantGrid",
            props={"variants": variant_payload},
            cycle_n=state_model.cycle_n,
        )
    )

    _emit(
        UIRenderEvent(
            type="ui_render",
            component="ChannelIntentPicker",
            props={"selected": state_model.outreach_channel},
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
            component="FeedbackPanel",
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
                component="FeedbackPanel",
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
        return "market_intelligence"
    return "end"
