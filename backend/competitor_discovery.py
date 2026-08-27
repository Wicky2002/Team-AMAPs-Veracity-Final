"""Live-search fallback for discovering real competitor domains for an
arbitrary topic, used when Claude-based inference is unavailable or fails.
Keeps competitor research from silently reverting to a hardcoded, possibly
wrong-domain default list regardless of what's actually being asked about.
"""

from __future__ import annotations

from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

DUCKDUCKGO_HTML_SEARCH_URL = "https://duckduckgo.com/html/"

# Aggregators, review sites, and generic platforms aren't "a competitor" to
# scrape directly -- exclude them so the discovered list is actual product
# companies, not directories that happen to rank for "X alternatives".
_BLOCKED_DOMAINS = {
    "wikipedia.org",
    "reddit.com",
    "youtube.com",
    "linkedin.com",
    "twitter.com",
    "x.com",
    "facebook.com",
    "instagram.com",
    "g2.com",
    "capterra.com",
    "trustpilot.com",
    "duckduckgo.com",
    "google.com",
    "crunchbase.com",
    "medium.com",
    "quora.com",
    "amazon.com",
}


def _root_domain(url: str) -> str | None:
    try:
        netloc = urlparse(url).netloc.lower()
    except Exception:
        return None
    netloc = netloc.removeprefix("www.")
    return netloc or None


async def discover_competitor_domains_via_search(topic: str, limit: int = 4) -> list[str]:
    query = f"{topic} competitors alternatives comparison"
    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
            response = await client.get(DUCKDUCKGO_HTML_SEARCH_URL, params={"q": query})
            response.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    domains: list[str] = []
    seen: set[str] = set()

    for result in soup.select("div.result")[:12]:
        link = result.select_one("a.result__a")
        if link is None:
            continue

        href = str(link.get("href", "")).strip()
        domain = _root_domain(href)
        if not domain or domain in seen or any(blocked in domain for blocked in _BLOCKED_DOMAINS):
            continue

        seen.add(domain)
        domains.append(domain)
        if len(domains) >= limit:
            break

    return domains
