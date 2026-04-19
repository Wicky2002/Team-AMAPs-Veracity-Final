from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from langgraph.config import get_stream_writer

from intent_router import detect_intent
from state import OutreachVariant, SignalReference


def _emit(payload: dict[str, Any]) -> None:
    """Emit streaming events when graph runs in custom stream mode."""
    try:
        writer = get_stream_writer()
        writer(payload)
    except Exception:
        # Safe no-op when stream writer is unavailable.
        pass


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _competitor_signals(message: str) -> list[dict[str, Any]]:
    await asyncio.sleep(0.05)
    return [
        {
            "type": "competitor",
            "source": "artisan-ai.com",
            "quote": "Competitors emphasize high-volume outbound; weak objection handling depth.",
            "confidence": 0.82,
            "context": f"Prompt context: {message[:120]}",
        },
        {
            "type": "competitor",
            "source": "11x.ai",
            "quote": "Strong email automation claims but limited cross-channel transparency.",
            "confidence": 0.78,
            "context": "Homepage + messaging summary",
        },
    ]


async def _pestel_signals() -> list[dict[str, Any]]:
    await asyncio.sleep(0.05)
    return [
        {
            "type": "pestel",
            "source": "news_scan",
            "quote": "More teams are demanding measurable attribution from AI SDR tooling.",
            "confidence": 0.71,
            "context": "Market trend synthesis",
        }
    ]


async def _audience_signals() -> list[dict[str, Any]]:
    await asyncio.sleep(0.05)
    return [
        {
            "type": "audience",
            "source": "reddit/r/sales",
            "quote": "Leaders are tired of generic personalization and fake context.",
            "confidence": 0.87,
            "context": "Top-voted thread language",
        }
    ]


async def intent_router_node(state: dict[str, Any]) -> dict[str, Any]:
    current_stage = str(state.get("loop_stage", "research"))
    message = str(state.get("message", ""))

    _emit({"type": "node_started", "node": "intent_router", "at": _utc_now_iso()})

    intent = detect_intent(message=message, current_stage=current_stage)
    stage_map = {
        "research": "research",
        "generate": "generate",
        "ab": "ab",
        "feedback": "feedback",
    }
    next_stage = stage_map.get(intent, current_stage)

    _emit(
        {
            "type": "intent_detected",
            "intent": intent,
            "loop_stage": next_stage,
            "message": f"Detected intent: {intent}",
        }
    )

    return {"loop_stage": next_stage}


async def market_intelligence_node(state: dict[str, Any]) -> dict[str, Any]:
    _emit({"type": "node_started", "node": "market_intelligence", "at": _utc_now_iso()})

    message = str(state.get("message", ""))
    results = await asyncio.gather(
        _competitor_signals(message),
        _pestel_signals(),
        _audience_signals(),
        return_exceptions=True,
    )

    signals: list[dict[str, Any]] = []
    for result in results:
        if isinstance(result, Exception):
            _emit(
                {
                    "type": "warning",
                    "code": "STALE_SIGNAL_FALLBACK",
                    "message": "A signal source failed, using available signals and continuing.",
                }
            )
            continue
        signals.extend(result)

    for signal in signals:
        _emit({"type": "signal_found", **signal})

    _emit(
        {
            "type": "ui_render",
            "component": "SignalIntelligenceBoard",
            "props": {"signals": signals},
        }
    )

    history = list(state.get("campaign_history", []))
    history.append(
        {
            "stage": "research",
            "summary": f"Collected {len(signals)} market signals",
            "at": _utc_now_iso(),
        }
    )

    return {
        "loop_stage": "generate",
        "signals": signals,
        "campaign_history": history,
    }


async def content_gen_node(state: dict[str, Any]) -> dict[str, Any]:
    _emit({"type": "node_started", "node": "content_generation", "at": _utc_now_iso()})

    signals = list(state.get("signals", []))
    top = signals[:2]

    _emit(
        {
            "type": "step_update",
            "node": "content_generation",
            "message": f"Built structured content brief from {len(top)} high-confidence signals.",
            "progress": 0.55,
        }
    )

    history = list(state.get("campaign_history", []))
    history.append(
        {
            "stage": "generate",
            "summary": "Structured message angles prepared",
            "at": _utc_now_iso(),
        }
    )

    return {"loop_stage": "ab", "campaign_history": history}


async def ab_variant_node(state: dict[str, Any]) -> dict[str, Any]:
    _emit({"type": "node_started", "node": "ab_variant", "at": _utc_now_iso()})

    signals = list(state.get("signals", []))
    provenance = [
        SignalReference(
            source=str(s.get("source", "unknown")),
            quote=str(s.get("quote", "")),
            confidence=float(s.get("confidence", 0.5)),
        )
        for s in signals[:2]
    ]

    variants = [
        OutreachVariant(
            subject_line="Cut AI SDR noise with true objection handling",
            hook="Most AI SDR tools optimize volume, not conversion quality.",
            cta="Open to a 15-min teardown?",
            hypothesis="Competitor Gap angle",
            provenance_chain=provenance,
        ),
        OutreachVariant(
            subject_line="3x reply-rate path for AI SDR outreach",
            hook="Teams switching to measured, context-rich outreach are seeing better replies.",
            cta="Want the ROI playbook?",
            hypothesis="ROI angle",
            provenance_chain=provenance,
        ),
    ]

    variant_payload = [v.model_dump() for v in variants]

    _emit(
        {
            "type": "ui_render",
            "component": "ABVariantGrid",
            "props": {"variants": variant_payload},
        }
    )

    history = list(state.get("campaign_history", []))
    history.append(
        {
            "stage": "ab",
            "summary": "Rendered two hypothesis-tagged outreach variants",
            "at": _utc_now_iso(),
        }
    )

    return {"variants": variant_payload, "loop_stage": "ab", "campaign_history": history}


async def outreach_node(state: dict[str, Any]) -> dict[str, Any]:
    _emit({"type": "node_started", "node": "outreach", "at": _utc_now_iso()})

    selected_channel = state.get("outreach_channel") or "LinkedIn"

    _emit(
        {
            "type": "ui_render",
            "component": "ChannelIntentPicker",
            "props": {"selected": selected_channel},
        }
    )

    metrics = [
        {"variant": 0, "open_rate": 0.44, "reply_rate": 0.11, "click_rate": 0.08},
        {"variant": 1, "open_rate": 0.49, "reply_rate": 0.18, "click_rate": 0.1},
    ]

    _emit(
        {
            "type": "ui_render",
            "component": "FeedbackPanel",
            "props": {"metrics": metrics},
        }
    )

    history = list(state.get("campaign_history", []))
    history.append(
        {
            "stage": "outreach",
            "summary": f"Simulated outreach on {selected_channel}",
            "at": _utc_now_iso(),
        }
    )

    return {"ab_results": metrics, "loop_stage": "feedback", "campaign_history": history}


async def feedback_ingestor_node(state: dict[str, Any]) -> dict[str, Any]:
    _emit({"type": "node_started", "node": "feedback_ingestor", "at": _utc_now_iso()})

    feedback_events = list(state.get("feedback_events", []))
    history = list(state.get("campaign_history", []))

    if feedback_events:
        history.append(
            {
                "stage": "feedback",
                "summary": "Feedback received and queued for next research cycle",
                "at": _utc_now_iso(),
            }
        )

    _emit(
        {
            "type": "ui_render",
            "component": "CampaignTimeline",
            "props": {"entries": history},
        }
    )

    return {"campaign_history": history, "loop_stage": "feedback"}


def route_after_feedback(state: dict[str, Any]) -> str:
    # If feedback exists, close the loop and continue with a new research pass.
    if state.get("feedback_events"):
        return "market_intelligence"
    return "end"
