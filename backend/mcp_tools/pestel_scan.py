from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup

from geo_context import build_topic_query_variants, get_serpapi_geo_params
from state import SignalReference

_SERP_API_ENDPOINT = "https://serpapi.com/search.json"
_NEWSAPI_ENDPOINT = "https://newsapi.org/v2/everything"
_GOOGLE_TRENDS_RSS = "https://trends.google.com/trends/trendingsearches/daily/rss"
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


def _pestel_query_variants(topic: str) -> list[str]:
    return build_topic_query_variants(topic, max_queries=6)


def _geo_params_for_topic(topic: str) -> dict[str, Any]:
    return get_serpapi_geo_params(topic)


def _dedupe_signals(signals: list[SignalReference]) -> list[SignalReference]:
    deduped: list[SignalReference] = []
    seen: set[tuple[str, str]] = set()

    for signal in signals:
        key = (signal.source_url.strip(), signal.raw_quote.strip().lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(signal)

    return deduped


def _topic_tokens(topic: str) -> set[str]:
    tokens = {
        token
        for token in re.findall(r"[a-zA-Z0-9]+", (topic or "").lower())
        if len(token) >= 4
    }
    return tokens


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


def _newsapi_key() -> str:
    return os.getenv("NEWS_API_KEY", "").strip() or os.getenv("NEWSAPI_KEY", "").strip()


def _parse_newsapi(payload: dict[str, Any]) -> list[SignalReference]:
    articles = payload.get("articles")
    if not isinstance(articles, list):
        return []

    signals: list[SignalReference] = []
    for article in articles[:5]:
        if not isinstance(article, dict):
            continue

        title = str(article.get("title", "")).strip()
        description = str(article.get("description", "")).strip()
        if not title and not description:
            continue

        combined = (title or description)[:220]
        source_meta = article.get("source")
        source_name = "newsapi"
        if isinstance(source_meta, dict):
            source_name = str(source_meta.get("name", "newsapi")).strip() or "newsapi"

        source_url = str(article.get("url", "")).strip() or "https://newsapi.org/"
        signals.append(
            SignalReference(
                source_type="pestel",
                source=f"newsapi:{source_name}",
                source_url=source_url,
                content=combined,
                quote=combined,
                raw_quote=combined,
                confidence=0.67,
            )
        )

    return signals


async def _scan_newsapi(topic: str, geo_params: dict[str, Any]) -> list[SignalReference]:
    api_key = _newsapi_key()
    if not api_key:
        return []

    query = (topic or "AI sales automation").strip() or "AI sales automation"
    language = str(geo_params.get("hl", "en")).split("-")[0]
    if not language:
        language = "en"

    params: dict[str, Any] = {
        "apiKey": api_key,
        "q": query,
        "pageSize": 5,
        "sortBy": "publishedAt",
        "language": language,
    }

    async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
        response = await client.get(_NEWSAPI_ENDPOINT, params=params)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            body_preview = exc.response.text[:220].replace("\n", " ")
            raise RuntimeError(f"NewsAPI HTTP {exc.response.status_code}: {body_preview}") from exc

        payload = response.json()

    if isinstance(payload, dict) and payload.get("status") == "error":
        raise RuntimeError(f"NewsAPI error: {payload.get('message', 'unknown error')}")

    if not isinstance(payload, dict):
        return []

    return _parse_newsapi(payload)


async def _scan_google_trends_rss(topic: str, geo_params: dict[str, Any]) -> list[SignalReference]:
    geo = str(geo_params.get("geo", "")).strip().upper()
    if not geo or len(geo) > 2:
        geo = "US"

    async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
        response = await client.get(_GOOGLE_TRENDS_RSS, params={"geo": geo})
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "xml")
    items = soup.find_all("item")
    if not items:
        return []

    tokens = _topic_tokens(topic)
    signals: list[SignalReference] = []
    for item in items[:12]:
        title_node = item.find("title")
        if title_node is None:
            continue

        title = str(title_node.get_text(" ", strip=True)).strip()
        if not title:
            continue

        if tokens:
            title_tokens = _topic_tokens(title)
            if not (tokens & title_tokens):
                continue

        source_url = f"https://trends.google.com/trends/explore?q={quote_plus(title)}&geo={geo}"
        text = f"Google Trends daily topic in {geo}: {title}"
        signals.append(
            SignalReference(
                source_type="pestel",
                source="google_trends_rss",
                source_url=source_url,
                content=text,
                quote=text,
                raw_quote=text,
                confidence=0.58,
            )
        )

        if len(signals) >= 4:
            break

    return signals


async def scan_pestel_trends(topic: str) -> list[SignalReference]:
    """Collect macro market signals via SerpAPI Trends + Google News."""
    _set_last_pestel_error(None)
    signals: list[SignalReference] = []
    diagnostics: list[str] = []

    geo_params = _geo_params_for_topic(topic)
    query_variants = _pestel_query_variants(topic)

    for query in query_variants:
        try:
            trends_params: dict[str, Any] = {"engine": "google_trends", "q": query}
            if "geo" in geo_params:
                trends_params["geo"] = geo_params["geo"]

            trends_payload = await _query_serpapi(trends_params)
            trend_signals = _parse_trends(query, trends_payload)
            signals.extend(trend_signals)
            if not trend_signals:
                diagnostics.append(f"Google Trends returned no interest_over_time rows for '{query}'")
        except Exception as exc:
            diagnostics.append(f"Google Trends request failed for '{query}' ({str(exc)})")
            try:
                trends_rss_signals = await _scan_google_trends_rss(query, geo_params)
                signals.extend(trends_rss_signals)
                if not trends_rss_signals:
                    diagnostics.append(f"Google Trends RSS returned no matching topics for '{query}'")
            except Exception as rss_exc:
                diagnostics.append(f"Google Trends RSS failed for '{query}' ({str(rss_exc)})")

        try:
            news_params: dict[str, Any] = {"engine": "google_news", "q": query, "num": 5}
            if "gl" in geo_params:
                news_params["gl"] = geo_params["gl"]
            if "hl" in geo_params:
                news_params["hl"] = geo_params["hl"]

            news_payload = await _query_serpapi(news_params)
            news_signals = _parse_news(news_payload)
            signals.extend(news_signals)
            if not news_signals:
                diagnostics.append(f"Google News returned no news_results rows for '{query}'")
        except Exception as exc:
            diagnostics.append(f"Google News request failed for '{query}' ({str(exc)})")
            try:
                newsapi_signals = await _scan_newsapi(query, geo_params)
                signals.extend(newsapi_signals)
                if not newsapi_signals:
                    diagnostics.append(f"NewsAPI returned no articles for '{query}'")
            except Exception as news_exc:
                diagnostics.append(f"NewsAPI request failed for '{query}' ({str(news_exc)})")

        if signals:
            break

    signals = _dedupe_signals(signals)

    if not signals and diagnostics:
        _set_last_pestel_error("; ".join(diagnostics)[:420])

    return signals
