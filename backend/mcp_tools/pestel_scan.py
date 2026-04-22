from __future__ import annotations

import os
from typing import Any

import httpx

from state import SignalReference

_SERP_API_ENDPOINT = "https://serpapi.com/search.json"
_last_pestel_error: str | None = None


def _set_last_pestel_error(message: str | None) -> None:
    global _last_pestel_error
    cleaned = (message or "").strip()
    _last_pestel_error = cleaned or None


def get_last_pestel_error() -> str | None:
    return _last_pestel_error


def _try_float(value: Any, default: float = 0.7) -> float:
    try:
        return float(value)
    except Exception:
        return default


async def _query_serpapi(params: dict[str, Any]) -> dict[str, Any]:
    api_key = os.getenv("SERP_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("SERP_API_KEY is missing")

    req_params = {**params, "api_key": api_key}
    async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
        response = await client.get(_SERP_API_ENDPOINT, params=req_params)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            body_preview = exc.response.text[:220].replace("\n", " ")
            raise RuntimeError(f"SerpAPI HTTP {exc.response.status_code}: {body_preview}") from exc

        payload = response.json()
        if isinstance(payload, dict) and payload.get("error"):
            raise RuntimeError(f"SerpAPI API error: {payload.get('error')}")

        if isinstance(payload, dict):
            return payload
        return {}


def _parse_trends(topic: str, payload: dict[str, Any]) -> list[SignalReference]:
    interest = payload.get("interest_over_time")
    if not isinstance(interest, list) or not interest:
        return []

    last_points = [point for point in interest[-8:] if isinstance(point, dict)]
    values = [_try_float(point.get("extracted_value", point.get("value", 0.0)), 0.0) for point in last_points]

    if not values:
        return []

    avg = sum(values) / max(len(values), 1)
    peak = max(values)
    signal_text = f"Google Trends for '{topic}' shows avg interest {avg:.1f} with peak {peak:.1f} in recent periods."

    return [
        SignalReference(
            source_type="pestel",
            source="google_trends",
            source_url="https://trends.google.com/",
            content=signal_text,
            quote=signal_text,
            raw_quote=signal_text,
            confidence=0.7,
        )
    ]


def _parse_news(payload: dict[str, Any]) -> list[SignalReference]:
    news_results = payload.get("news_results")
    if not isinstance(news_results, list):
        return []

    signals: list[SignalReference] = []
    for result in news_results[:5]:
        if not isinstance(result, dict):
            continue

        title = str(result.get("title", "")).strip()
        if not title:
            continue

        source_url = str(result.get("link", "")).strip() or "https://news.google.com/"
        source_name = str(result.get("source", "news"))

        signals.append(
            SignalReference(
                source_type="pestel",
                source=f"news:{source_name}",
                source_url=source_url,
                content=title[:220],
                quote=title[:220],
                raw_quote=title[:220],
                confidence=0.65,
            )
        )

    return signals


async def scan_pestel_trends(topic: str) -> list[SignalReference]:
    """Collect macro market signals via SerpAPI Trends + Google News."""
    _set_last_pestel_error(None)
    signals: list[SignalReference] = []
    diagnostics: list[str] = []

    try:
        trends_payload = await _query_serpapi({"engine": "google_trends", "q": topic})
        trend_signals = _parse_trends(topic, trends_payload)
        signals.extend(trend_signals)
        if not trend_signals:
            diagnostics.append("Google Trends returned no interest_over_time rows")
    except Exception as exc:
        diagnostics.append(f"Google Trends request failed ({str(exc)})")

    try:
        news_payload = await _query_serpapi({"engine": "google_news", "q": topic, "num": 5})
        news_signals = _parse_news(news_payload)
        signals.extend(news_signals)
        if not news_signals:
            diagnostics.append("Google News returned no news_results rows")
    except Exception as exc:
        diagnostics.append(f"Google News request failed ({str(exc)})")

    if not signals and diagnostics:
        _set_last_pestel_error("; ".join(diagnostics)[:420])

    return signals
