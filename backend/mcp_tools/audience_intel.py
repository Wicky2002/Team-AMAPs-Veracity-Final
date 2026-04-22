from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import quote, quote_plus

import httpx

from state import SignalReference

SUBREDDITS: tuple[str, ...] = ("sales", "saleshacking", "B2Bsales", "startups")
DEFAULT_TIMEOUT_SECONDS = 10.0
APIFY_API_BASE_URL = "https://api.apify.com/v2"

_DEFAULT_HEADERS = {
    "User-Agent": "Veracity/1.0 (hackathon research bot)",
    "Accept": "application/json",
}


def _headers() -> dict[str, str]:
    user_agent = os.getenv("REDDIT_USER_AGENT", _DEFAULT_HEADERS["User-Agent"]).strip()
    return {
        **_DEFAULT_HEADERS,
        "User-Agent": user_agent or _DEFAULT_HEADERS["User-Agent"],
    }


def _first_str(payload: dict[str, Any], keys: list[str]) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _first_int(payload: dict[str, Any], keys: list[str]) -> int | None:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        try:
            return int(value)
        except Exception:
            continue
    return None


def _to_reddit_url(permalink: str, subreddit: str) -> str:
    cleaned = (permalink or "").strip()
    if cleaned.startswith("http://") or cleaned.startswith("https://"):
        return cleaned
    if cleaned.startswith("/"):
        return f"https://www.reddit.com{cleaned}"
    return f"https://www.reddit.com/r/{subreddit}"


def _normalized_subreddit(value: str) -> str:
    subreddit = (value or "").strip().lower()
    if not subreddit:
        return ""

    subreddit = subreddit.replace("https://www.reddit.com/r/", "")
    subreddit = subreddit.replace("http://www.reddit.com/r/", "")
    subreddit = subreddit.replace("www.reddit.com/r/", "")
    subreddit = subreddit.replace("reddit.com/r/", "")
    subreddit = subreddit.replace("/r/", "")
    subreddit = subreddit.replace("r/", "")
    return subreddit.strip("/")


def _safe_json_env_dict(name: str) -> dict[str, Any] | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None

    try:
        parsed = json.loads(raw)
    except Exception:
        return None

    if isinstance(parsed, dict):
        return parsed
    return None


def _get_apify_token() -> str:
    return os.getenv("APIFY_TOKEN", "").strip()


def _get_apify_actor() -> str:
    return os.getenv("APIFY_REDDIT_ACTOR", "spry_wholemeal/reddit-scraper").strip() or "spry_wholemeal/reddit-scraper"


def _get_apify_max_items(limit_per_subreddit: int) -> int:
    raw = os.getenv("APIFY_REDDIT_MAX_ITEMS", "").strip()
    if raw:
        try:
            return max(1, min(int(raw), 200))
        except Exception:
            pass

    derived = max(10, limit_per_subreddit * len(SUBREDDITS) * 2)
    return min(derived, 200)


def _topic_start_urls(topic: str, limit_per_subreddit: int) -> list[dict[str, str]]:
    encoded = quote_plus((topic or "AI SDR").strip() or "AI SDR")
    urls: list[dict[str, str]] = []

    for subreddit in SUBREDDITS:
        urls.append(
            {
                "url": (
                    f"https://www.reddit.com/r/{subreddit}/search/?q={encoded}&sort=top&t=year"
                    f"&limit={max(1, min(limit_per_subreddit, 50))}"
                )
            }
        )

    urls.append({"url": "https://www.reddit.com/r/sales/top/?t=month"})
    return urls


def _confidence_from_score(score: int | None) -> float:
    safe_score = float(score or 0)
    return float(min(0.5 + (safe_score / 5000.0), 0.95))


def _signals_from_listing(
    payload: dict[str, Any],
    *,
    subreddit: str,
    include_selftext: bool,
) -> list[SignalReference]:
    listing = payload.get("data")
    if not isinstance(listing, dict):
        return []

    children = listing.get("children")
    if not isinstance(children, list):
        return []

    results: list[SignalReference] = []
    for child in children:
        if not isinstance(child, dict):
            continue

        post = child.get("data")
        if not isinstance(post, dict):
            continue

        title = str(post.get("title", "")).strip()
        if not title:
            continue

        source_url = _to_reddit_url(str(post.get("permalink", "")), subreddit)
        confidence = _confidence_from_score(int(post.get("score", 0) or 0))

        title_text = title[:220]
        results.append(
            SignalReference(
                source_type="audience",
                source=f"reddit/r/{subreddit}",
                source_url=source_url,
                content=title_text,
                quote=title_text,
                raw_quote=title_text,
                confidence=confidence,
            )
        )

        if not include_selftext:
            continue

        selftext = str(post.get("selftext", "")).strip()
        if len(selftext) < 60:
            continue

        excerpt = selftext[:220]
        results.append(
            SignalReference(
                source_type="audience",
                source=f"reddit/r/{subreddit}",
                source_url=source_url,
                content=excerpt,
                quote=excerpt,
                raw_quote=excerpt,
                confidence=max(0.65, confidence * 0.85),
            )
        )

    return results


def _dedupe_signals(signals: list[SignalReference]) -> list[SignalReference]:
    deduped: list[SignalReference] = []
    seen: set[tuple[str, str]] = set()

    for signal in signals:
        key = (signal.source_url or "", signal.raw_quote.strip().lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(signal)

    return deduped


async def _fetch_listing_signals(
    client: httpx.AsyncClient,
    *,
    subreddit: str,
    endpoint: str,
    params: dict[str, Any],
    include_selftext: bool,
) -> list[SignalReference]:
    url = f"https://www.reddit.com/r/{subreddit}/{endpoint}.json"

    try:
        response = await client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return []

    if not isinstance(payload, dict):
        return []

    return _signals_from_listing(payload, subreddit=subreddit, include_selftext=include_selftext)


async def _fetch_apify_actor_schema(
    client: httpx.AsyncClient,
    *,
    actor_id: str,
) -> dict[str, Any] | None:
    safe_actor_id = quote(actor_id, safe="")
    url = f"{APIFY_API_BASE_URL}/acts/{safe_actor_id}"

    try:
        response = await client.get(url)
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return None

    if not isinstance(payload, dict):
        return None

    data = payload.get("data")
    if not isinstance(data, dict):
        return None

    input_schema = data.get("inputSchema")
    if isinstance(input_schema, dict):
        return input_schema

    return None


def _dedupe_payload_dicts(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()

    for payload in payloads:
        try:
            key = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        except Exception:
            key = str(payload)

        if key in seen:
            continue
        seen.add(key)
        deduped.append(payload)

    return deduped


def _build_apify_actor_inputs(
    *,
    topic: str,
    limit_per_subreddit: int,
    input_schema: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []

    explicit = _safe_json_env_dict("APIFY_REDDIT_INPUT_JSON")
    if explicit is not None:
        payloads.append(explicit)

    normalized_topic = (topic or "AI SDR").strip() or "AI SDR"
    max_items = _get_apify_max_items(limit_per_subreddit)
    subreddits = list(SUBREDDITS)
    start_urls = _topic_start_urls(normalized_topic, limit_per_subreddit)

    properties = input_schema.get("properties") if isinstance(input_schema, dict) else None
    property_names = set(properties.keys()) if isinstance(properties, dict) else set()

    # Unknown schema: try actor-specific templates first, then a generic fallback.
    if not property_names:
        payloads.extend(
            [
                {
                    "mode": "search",
                    "search": {
                        "queries": [normalized_topic],
                        "targets": subreddits,
                    },
                },
                {
                    "mode": "search",
                    "search": {
                        "queries": [normalized_topic],
                    },
                },
                {
                    "mode": "scrape",
                    "scrape": {
                        "subreddits": subreddits,
                    },
                },
                {
                    "query": normalized_topic,
                    "subreddits": subreddits,
                    "limit": max_items,
                    "sort": "top",
                    "time": "year",
                    "startUrls": start_urls,
                },
            ]
        )
        return _dedupe_payload_dicts(payloads)

    payload: dict[str, Any] = {}

    def set_if_present(candidates: list[str], value: Any):
        for candidate in candidates:
            if candidate in property_names:
                payload[candidate] = value

    set_if_present(["query", "search", "searchTerm", "searchQuery", "keyword", "keywords"], normalized_topic)
    set_if_present(["subreddits", "communities", "subredditNames", "subredditList"], subreddits)
    set_if_present(["subreddit", "community"], "sales")
    set_if_present(["limit", "maxItems", "maxResults", "resultsLimit", "postsLimit", "maxPosts"], max_items)
    set_if_present(["sort", "sortBy", "postSort"], "top")
    set_if_present(["time", "timeFilter", "timeRange", "period"], "year")

    if "startUrls" in property_names:
        payload["startUrls"] = start_urls
    if "urls" in property_names:
        payload["urls"] = [entry["url"] for entry in start_urls]

    if payload:
        payloads.append(payload)
    else:
        payloads.extend(
            [
                {
                    "mode": "search",
                    "search": {
                        "queries": [normalized_topic],
                        "targets": subreddits,
                    },
                },
                {
                    "mode": "search",
                    "search": {
                        "queries": [normalized_topic],
                    },
                },
            ]
        )

    return _dedupe_payload_dicts(payloads)


def _normalize_apify_signal_source(item: dict[str, Any]) -> tuple[str, str]:
    subreddit_value = _first_str(
        item,
        ["subreddit", "subredditName", "subreddit_name_prefixed", "community", "sourceSubreddit"],
    )
    subreddit = _normalized_subreddit(subreddit_value) or "sales"
    return f"reddit/r/{subreddit}", subreddit


def _to_apify_reddit_url(item: dict[str, Any], subreddit: str) -> str:
    candidate = _first_str(item, ["postUrl", "postURL", "url", "link", "permalink"]) or ""
    if candidate.startswith("http://") or candidate.startswith("https://"):
        return candidate
    if candidate.startswith("/"):
        return f"https://www.reddit.com{candidate}"
    return f"https://www.reddit.com/r/{subreddit}"


def _signals_from_apify_items(items: list[dict[str, Any]]) -> list[SignalReference]:
    allowed_subreddits = {subreddit.lower() for subreddit in SUBREDDITS}
    signals: list[SignalReference] = []

    for raw_item in items:
        if not isinstance(raw_item, dict):
            continue

        item = raw_item.get("data") if isinstance(raw_item.get("data"), dict) else raw_item
        if not isinstance(item, dict):
            continue

        source, subreddit = _normalize_apify_signal_source(item)
        if subreddit.lower() not in allowed_subreddits:
            continue
        source_url = _to_apify_reddit_url(item, subreddit)

        score = _first_int(item, ["score", "upvotes", "upvoteCount", "ups", "points"])
        confidence = _confidence_from_score(score)

        title = _first_str(item, ["title", "postTitle", "headline", "name"])
        if title:
            clipped = title[:220]
            signals.append(
                SignalReference(
                    source_type="audience",
                    source=source,
                    source_url=source_url,
                    content=clipped,
                    quote=clipped,
                    raw_quote=clipped,
                    confidence=confidence,
                )
            )

        body = _first_str(item, ["selftext", "text", "body", "content", "description", "postText"])
        if len(body) >= 60:
            excerpt = body[:220]
            signals.append(
                SignalReference(
                    source_type="audience",
                    source=source,
                    source_url=source_url,
                    content=excerpt,
                    quote=excerpt,
                    raw_quote=excerpt,
                    confidence=max(0.65, confidence * 0.85),
                )
            )

    return signals


async def _scan_audience_intent_with_apify(topic: str, limit_per_subreddit: int) -> list[SignalReference]:
    token = _get_apify_token()
    if not token:
        return []

    actor_id = _get_apify_actor()
    max_items = _get_apify_max_items(limit_per_subreddit)
    safe_actor_id = quote(actor_id, safe="")

    async with httpx.AsyncClient(
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": _headers()["User-Agent"],
        },
        timeout=60,
        follow_redirects=True,
    ) as client:
        input_schema = await _fetch_apify_actor_schema(client, actor_id=actor_id)
        actor_inputs = _build_apify_actor_inputs(
            topic=topic,
            limit_per_subreddit=limit_per_subreddit,
            input_schema=input_schema,
        )

        run_url = f"{APIFY_API_BASE_URL}/acts/{safe_actor_id}/run-sync-get-dataset-items"
        for actor_input in actor_inputs:
            try:
                response = await client.post(
                    run_url,
                    params={
                        "clean": "true",
                        "format": "json",
                        "limit": str(max_items),
                    },
                    json=actor_input,
                )
            except Exception:
                continue

            if response.status_code >= 400:
                continue

            try:
                payload = response.json()
            except Exception:
                continue

            if not isinstance(payload, list):
                continue

            typed_items = [item for item in payload if isinstance(item, dict)]
            if not typed_items:
                continue

            signals = _signals_from_apify_items(typed_items)
            if signals:
                return signals

    return []


async def scan_hot_posts(subreddit: str = "sales", limit: int = 10) -> list[SignalReference]:
    """Fetch top monthly posts from a subreddit via Reddit public JSON endpoints."""
    async with httpx.AsyncClient(
        headers=_headers(),
        timeout=DEFAULT_TIMEOUT_SECONDS,
        follow_redirects=True,
    ) as client:
        try:
            return await _fetch_listing_signals(
                client,
                subreddit=subreddit,
                endpoint="top",
                params={"t": "month", "limit": limit, "raw_json": 1},
                include_selftext=False,
            )
        except Exception:
            return []


async def scan_audience_intent(topic: str, limit_per_subreddit: int = 5) -> list[SignalReference]:
    """Scan audience intent using Apify Reddit Actor first, then direct Reddit JSON fallback."""
    apify_signals = await _scan_audience_intent_with_apify(topic, limit_per_subreddit)
    if apify_signals:
        return _dedupe_signals(apify_signals)

    signals: list[SignalReference] = []

    async with httpx.AsyncClient(
        headers=_headers(),
        timeout=DEFAULT_TIMEOUT_SECONDS,
        follow_redirects=True,
    ) as client:
        for subreddit in SUBREDDITS:
            subreddit_signals = await _fetch_listing_signals(
                client,
                subreddit=subreddit,
                endpoint="search",
                params={
                    "q": topic,
                    "sort": "top",
                    "t": "year",
                    "limit": limit_per_subreddit,
                    "restrict_sr": 1,
                    "raw_json": 1,
                },
                include_selftext=True,
            )
            signals.extend(subreddit_signals)

        # Add broader sentiment context from monthly top posts in r/sales.
        top_monthly = await _fetch_listing_signals(
            client,
            subreddit="sales",
            endpoint="top",
            params={"t": "month", "limit": 10, "raw_json": 1},
            include_selftext=False,
        )
        signals.extend(top_monthly)

    return _dedupe_signals(signals)
