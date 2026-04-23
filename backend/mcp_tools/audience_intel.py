from __future__ import annotations

import asyncio
import json
import re
import os
from typing import Any
from urllib.parse import quote, quote_plus

import httpx
from bs4 import BeautifulSoup

from geo_context import build_topic_query_variants, get_geo_subreddit_hints
from state import SignalReference

SUBREDDITS: tuple[str, ...] = ("sales", "saleshacking", "B2Bsales", "startups")
DEFAULT_TIMEOUT_SECONDS = 10.0
APIFY_API_BASE_URL = "https://api.apify.com/v2"
HN_ALGOLIA_API = "https://hn.algolia.com/api/v1/search"
YOUTUBE_SEARCH_URL = "https://www.youtube.com/results"
YOUTUBE_WATCH_URL = "https://www.youtube.com/watch"
DUCKDUCKGO_HTML_SEARCH_URL = "https://duckduckgo.com/html/"

_DEFAULT_HEADERS = {
    "User-Agent": "Veracity/1.0 (hackathon research bot)",
    "Accept": "application/json",
}


def _subreddits_for_topic(topic: str) -> tuple[str, ...]:
    candidates = list(SUBREDDITS)
    candidates.extend(list(get_geo_subreddit_hints(topic)))

    deduped: list[str] = []
    seen: set[str] = set()
    for subreddit in candidates:
        key = subreddit.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(subreddit)
    return tuple(deduped)


def _query_variants(topic: str) -> list[str]:
    return build_topic_query_variants(topic, max_queries=6)


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


def _clean_html_text(value: str) -> str:
    text = BeautifulSoup(value or "", "html.parser").get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _decode_json_escaped_text(raw: str) -> str:
    if not raw:
        return ""

    try:
        return json.loads(f'"{raw}"')
    except Exception:
        return raw


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


def _get_apify_max_items(limit_per_subreddit: int, subreddit_count: int | None = None) -> int:
    raw = os.getenv("APIFY_REDDIT_MAX_ITEMS", "").strip()
    if raw:
        try:
            return max(1, min(int(raw), 200))
        except Exception:
            pass

    subreddit_total = max(1, subreddit_count or len(SUBREDDITS))
    derived = max(10, limit_per_subreddit * subreddit_total * 2)
    return min(derived, 200)


def _topic_start_urls(topic: str, limit_per_subreddit: int, subreddits: tuple[str, ...] | None = None) -> list[dict[str, str]]:
    encoded = quote_plus((topic or "AI SDR").strip() or "AI SDR")
    urls: list[dict[str, str]] = []

    for subreddit in (subreddits or SUBREDDITS):
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


async def scan_hackernews(topic: str, hits_per_page: int = 10) -> list[SignalReference]:
    """Pull audience sentiment from Hacker News comments via Algolia API (no key)."""
    query = (topic or "AI SDR").strip() or "AI SDR"

    async with httpx.AsyncClient(
        headers=_headers(),
        timeout=DEFAULT_TIMEOUT_SECONDS,
        follow_redirects=True,
    ) as client:
        try:
            response = await client.get(
                HN_ALGOLIA_API,
                params={
                    "query": query,
                    "tags": "comment",
                    "hitsPerPage": max(1, min(hits_per_page, 30)),
                },
            )
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return []

    if not isinstance(payload, dict):
        return []

    hits = payload.get("hits")
    if not isinstance(hits, list):
        return []

    signals: list[SignalReference] = []
    for hit in hits:
        if not isinstance(hit, dict):
            continue

        comment_text = _clean_html_text(str(hit.get("comment_text", "")))
        if len(comment_text) < 40:
            continue

        object_id = str(hit.get("objectID", "")).strip()
        if not object_id:
            continue

        points = _first_int(hit, ["points"]) or 0
        confidence = min(0.95, 0.65 + (float(points) / 250.0))
        source_url = f"https://news.ycombinator.com/item?id={object_id}"

        excerpt = comment_text[:220]
        signals.append(
            SignalReference(
                source_type="audience",
                source="hackernews",
                source_url=source_url,
                content=excerpt,
                quote=excerpt,
                raw_quote=excerpt,
                confidence=confidence,
            )
        )

    return _dedupe_signals(signals)


async def scan_g2_reviews(topic: str, limit: int = 8) -> list[SignalReference]:
    """Collect public G2-linked audience snippets via free DuckDuckGo HTML search."""
    query = f"site:g2.com {((topic or 'AI SDR').strip() or 'AI SDR')} reviews"

    async with httpx.AsyncClient(
        headers=_headers(),
        timeout=DEFAULT_TIMEOUT_SECONDS,
        follow_redirects=True,
    ) as client:
        try:
            response = await client.get(
                DUCKDUCKGO_HTML_SEARCH_URL,
                params={"q": query},
            )
            response.raise_for_status()
        except Exception:
            return []

    soup = BeautifulSoup(response.text, "html.parser")
    signals: list[SignalReference] = []

    for result in soup.select("div.result")[: max(1, min(limit, 12))]:
        link = result.select_one("a.result__a")
        if link is None:
            continue

        href = str(link.get("href", "")).strip()
        if "g2.com" not in href:
            continue

        title = _clean_html_text(link.get_text(" ", strip=True))
        snippet = result.select_one("a.result__snippet") or result.select_one("div.result__snippet")
        snippet_text = _clean_html_text(snippet.get_text(" ", strip=True) if snippet else "")

        content = (snippet_text or title)[:220]
        if len(content) < 30:
            continue

        signals.append(
            SignalReference(
                source_type="audience",
                source="g2_public",
                source_url=href,
                content=content,
                quote=content,
                raw_quote=content,
                confidence=0.68,
            )
        )

    return _dedupe_signals(signals)


def _extract_youtube_video_ids(search_html: str, max_videos: int = 3) -> list[str]:
    ids = re.findall(r'"videoId":"([A-Za-z0-9_-]{11})"', search_html or "")
    deduped: list[str] = []
    seen: set[str] = set()
    for video_id in ids:
        if video_id in seen:
            continue
        seen.add(video_id)
        deduped.append(video_id)
        if len(deduped) >= max_videos:
            break
    return deduped


def _extract_comment_snippets_from_watch_html(watch_html: str, max_comments: int = 4) -> list[str]:
    if not watch_html:
        return []

    snippets: list[str] = []
    blocks = re.findall(
        r'"commentRenderer":\{"commentId":"[^"]+","contentText":\{"runs":\[(.*?)\]\}',
        watch_html,
    )

    for block in blocks:
        parts = re.findall(r'"text":"(.*?)"', block)
        if not parts:
            continue

        joined = " ".join(_decode_json_escaped_text(part) for part in parts)
        cleaned = _clean_html_text(joined)
        if len(cleaned) < 30:
            continue

        snippets.append(cleaned[:220])
        if len(snippets) >= max_comments:
            break

    return snippets


async def scan_youtube_comments(topic: str, max_videos: int = 3) -> list[SignalReference]:
    """Best-effort extraction of live YouTube comment snippets without API keys."""
    query = (topic or "AI SDR").strip() or "AI SDR"

    async with httpx.AsyncClient(
        headers=_headers(),
        timeout=DEFAULT_TIMEOUT_SECONDS,
        follow_redirects=True,
    ) as client:
        try:
            search_response = await client.get(
                YOUTUBE_SEARCH_URL,
                params={"search_query": query},
            )
            search_response.raise_for_status()
        except Exception:
            return []

        video_ids = _extract_youtube_video_ids(search_response.text, max_videos=max_videos)
        if not video_ids:
            return []

        signals: list[SignalReference] = []
        for video_id in video_ids:
            try:
                watch_response = await client.get(YOUTUBE_WATCH_URL, params={"v": video_id})
                watch_response.raise_for_status()
            except Exception:
                continue

            snippets = _extract_comment_snippets_from_watch_html(watch_response.text)
            for snippet in snippets:
                signals.append(
                    SignalReference(
                        source_type="audience",
                        source="youtube_comments",
                        source_url=f"https://www.youtube.com/watch?v={video_id}",
                        content=snippet,
                        quote=snippet,
                        raw_quote=snippet,
                        confidence=0.7,
                    )
                )

    return _dedupe_signals(signals)


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
    subreddits: tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []

    explicit = _safe_json_env_dict("APIFY_REDDIT_INPUT_JSON")
    if explicit is not None:
        payloads.append(explicit)

    normalized_topic = (topic or "AI SDR").strip() or "AI SDR"
    resolved_subreddits = tuple(subreddits or _subreddits_for_topic(normalized_topic))
    max_items = _get_apify_max_items(limit_per_subreddit, len(resolved_subreddits))
    subreddit_list = list(resolved_subreddits)
    start_urls = _topic_start_urls(normalized_topic, limit_per_subreddit, resolved_subreddits)
    queries = _query_variants(normalized_topic)

    properties = input_schema.get("properties") if isinstance(input_schema, dict) else None
    property_names = set(properties.keys()) if isinstance(properties, dict) else set()

    # Unknown schema: try actor-specific templates first, then a generic fallback.
    if not property_names:
        payloads.extend(
            [
                {
                    "mode": "search",
                    "search": {
                        "queries": queries,
                        "targets": subreddit_list,
                    },
                },
                {
                    "mode": "search",
                    "search": {
                        "queries": queries,
                    },
                },
                {
                    "mode": "scrape",
                    "scrape": {
                        "subreddits": subreddit_list,
                    },
                },
                {
                    "query": normalized_topic,
                    "subreddits": subreddit_list,
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
    set_if_present(["subreddits", "communities", "subredditNames", "subredditList"], subreddit_list)
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
                        "queries": queries,
                        "targets": subreddit_list,
                    },
                },
                {
                    "mode": "search",
                    "search": {
                        "queries": queries,
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


def _signals_from_apify_items(items: list[dict[str, Any]], *, allowed_subreddits: set[str] | None = None) -> list[SignalReference]:
    allowed = allowed_subreddits or {subreddit.lower() for subreddit in SUBREDDITS}
    signals: list[SignalReference] = []

    for raw_item in items:
        if not isinstance(raw_item, dict):
            continue

        item = raw_item.get("data") if isinstance(raw_item.get("data"), dict) else raw_item
        if not isinstance(item, dict):
            continue

        source, subreddit = _normalize_apify_signal_source(item)
        if subreddit.lower() not in allowed:
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
    subreddits = _subreddits_for_topic(topic)
    max_items = _get_apify_max_items(limit_per_subreddit, len(subreddits))
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
            subreddits=subreddits,
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

            signals = _signals_from_apify_items(
                typed_items,
                allowed_subreddits={subreddit.lower() for subreddit in subreddits},
            )
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
    try:
        from mcp_tools.job_signals import scan_job_market_signals
    except Exception:
        scan_job_market_signals = None  # type: ignore[assignment]

    apify_signals = await _scan_audience_intent_with_apify(topic, limit_per_subreddit)
    reddit_signals: list[SignalReference] = []

    if apify_signals:
        reddit_signals = apify_signals
    else:
        subreddits = _subreddits_for_topic(topic)
        query_variants = _query_variants(topic)

        async with httpx.AsyncClient(
            headers=_headers(),
            timeout=DEFAULT_TIMEOUT_SECONDS,
            follow_redirects=True,
        ) as client:
            for subreddit in subreddits:
                for query in query_variants:
                    subreddit_signals = await _fetch_listing_signals(
                        client,
                        subreddit=subreddit,
                        endpoint="search",
                        params={
                            "q": query,
                            "sort": "top",
                            "t": "year",
                            "limit": limit_per_subreddit,
                            "restrict_sr": 1,
                            "raw_json": 1,
                        },
                        include_selftext=True,
                    )
                    reddit_signals.extend(subreddit_signals)

            # Add broader sentiment context from monthly top posts in r/sales.
            monthly_targets = ["sales"]
            for geo_subreddit in get_geo_subreddit_hints(topic):
                if geo_subreddit not in monthly_targets:
                    monthly_targets.append(geo_subreddit)

            for monthly_subreddit in monthly_targets:
                top_monthly = await _fetch_listing_signals(
                    client,
                    subreddit=monthly_subreddit,
                    endpoint="top",
                    params={"t": "month", "limit": 10, "raw_json": 1},
                    include_selftext=False,
                )
                reddit_signals.extend(top_monthly)

    tasks: list[Any] = [
        scan_hackernews(topic),
        scan_g2_reviews(topic),
        scan_youtube_comments(topic),
    ]
    if scan_job_market_signals is not None:
        tasks.append(scan_job_market_signals(topic))

    extra_results = await asyncio.gather(*tasks, return_exceptions=True)

    signals = list(reddit_signals)
    for result in extra_results:
        if isinstance(result, Exception):
            continue
        signals.extend(result)

    return _dedupe_signals(signals)
