from __future__ import annotations

from typing import Any

import httpx
from bs4 import BeautifulSoup


async def scrape_competitor(domain: str) -> dict[str, Any]:
    """Phase-4 skeleton stub for live-signal scraping.

    This intentionally keeps extraction simple; replace selectors with domain-specific logic.
    """
    url = domain if domain.startswith("http") else f"https://{domain}"

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(url)
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    heading_candidates = [
        tag.get_text(" ", strip=True)
        for tag in soup.select("h1, h2")[:5]
        if tag.get_text(strip=True)
    ]

    cta_candidates = [
        tag.get_text(" ", strip=True)
        for tag in soup.select("a, button")[:20]
        if 3 <= len(tag.get_text(strip=True)) <= 80
    ]

    return {
        "domain": domain,
        "taglines": heading_candidates[:3],
        "pain_points": heading_candidates[3:5],
        "ctas": cta_candidates[:5],
    }
