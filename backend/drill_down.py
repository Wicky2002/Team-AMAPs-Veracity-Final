"""One-level-deeper sub-investigation on a specific signal ("drill into this
thread"). Bounded depth budget by design: exactly one follow-up search per
call, no recursion. Source-agnostic -- works for any signal, regardless of
which of the five collectors originally produced it.
"""

from __future__ import annotations

import httpx
from bs4 import BeautifulSoup

from state import SignalReference

DUCKDUCKGO_HTML_SEARCH_URL = "https://duckduckgo.com/html/"


async def drill_into_signal(*, quote: str, source: str, source_type: str) -> list[SignalReference]:
    """Run one targeted follow-up search seeded by an existing signal's exact
    claim, to surface more specific supporting detail on that thread."""
    query = f'"{quote[:120]}" details data evidence'
    results: list[SignalReference] = []

    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
            response = await client.get(DUCKDUCKGO_HTML_SEARCH_URL, params={"q": query})
            response.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    for result in soup.select("div.result")[:6]:
        link = result.select_one("a.result__a")
        snippet_node = result.select_one("a.result__snippet") or result.select_one("div.result__snippet")
        if link is None or snippet_node is None:
            continue

        href = str(link.get("href", "")).strip()
        snippet = snippet_node.get_text(" ", strip=True)
        if len(snippet) < 30 or snippet.strip() == quote.strip():
            continue

        results.append(
            SignalReference(
                source_type=source_type,  # type: ignore[arg-type]
                source=f"{source} (deep dive)",
                source_url=href or None,
                content=snippet,
                quote=snippet,
                raw_quote=snippet,
                confidence=0.58,
            )
        )
        if len(results) >= 2:
            break

    return results
