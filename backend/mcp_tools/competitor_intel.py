from __future__ import annotations

import os
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from state import SignalReference

TARGETS = ["artisan.co", "11x.ai", "regie.ai"]
DUCKDUCKGO_HTML_SEARCH_URL = "https://duckduckgo.com/html/"
SERP_API_ENDPOINT = "https://serpapi.com/search.json"


def _normalize_root(domain: str) -> str:
    parsed = urlparse(domain)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    clean = domain.replace("https://", "").replace("http://", "").strip("/")
    return f"https://{clean}"


def _link_matches(href: str) -> bool:
    lowered = href.lower()
    return any(token in lowered for token in ["/pricing", "/vs-", "/vs/", "/compare", "comparison"])


def _extract_competitor_paragraphs(soup: BeautifulSoup) -> list[str]:
    paragraphs: list[str] = []
    for p in soup.find_all("p")[:12]:
        text = p.get_text(" ", strip=True)
        if len(text) >= 40:
            paragraphs.append(text[:220])
        if len(paragraphs) >= 5:
            break
    return paragraphs


def _extract_search_snippets(html: str, limit: int = 4) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    snippets: list[tuple[str, str]] = []

    for result in soup.select("div.result")[: max(1, min(limit, 10))]:
        link = result.select_one("a.result__a")
        snippet_node = result.select_one("a.result__snippet") or result.select_one("div.result__snippet")
        if link is None or snippet_node is None:
            continue

        href = str(link.get("href", "")).strip()
        snippet = snippet_node.get_text(" ", strip=True)
        if len(snippet) < 30:
            continue

        snippets.append((href, snippet[:220]))

    return snippets


async def _duckduckgo_competitor_snippets(client: httpx.AsyncClient, domain: str) -> list[SignalReference]:
    query = f"{domain} pricing alternatives comparison"
    response = await client.get(DUCKDUCKGO_HTML_SEARCH_URL, params={"q": query})
    response.raise_for_status()

    signals: list[SignalReference] = []
    for href, snippet in _extract_search_snippets(response.text, limit=4):
        signals.append(
            _make_signal(
                source=domain,
                source_url=href or f"https://{domain}",
                content=snippet,
                raw_quote=snippet,
                confidence=0.62,
            )
        )

    return signals


async def _serpapi_competitor_snippets(domain: str) -> list[SignalReference]:
    api_key = os.getenv("SERP_API_KEY", "").strip()
    if not api_key:
        return []

    params = {
        "engine": "google",
        "q": f"{domain} pricing alternatives comparison",
        "api_key": api_key,
        "num": 5,
    }

    async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
        response = await client.get(SERP_API_ENDPOINT, params=params)
        response.raise_for_status()
        payload = response.json()

    if not isinstance(payload, dict):
        return []

    organic = payload.get("organic_results")
    if not isinstance(organic, list):
        return []

    signals: list[SignalReference] = []
    for result in organic[:4]:
        if not isinstance(result, dict):
            continue

        snippet = str(result.get("snippet", "")).strip()
        if len(snippet) < 30:
            continue

        source_url = str(result.get("link", "")).strip() or f"https://{domain}"
        signals.append(
            _make_signal(
                source=domain,
                source_url=source_url,
                content=snippet[:220],
                raw_quote=snippet[:220],
                confidence=0.66,
            )
        )

    return signals


def _make_signal(
    *,
    source: str,
    source_url: str,
    content: str,
    raw_quote: str,
    confidence: float,
) -> SignalReference:
    return SignalReference(
        source_type="competitor",
        source=source,
        source_url=source_url,
        content=content,
        quote=raw_quote,
        raw_quote=raw_quote,
        confidence=confidence,
    )


async def scrape_competitor(domain: str) -> list[SignalReference]:
    """Scrape competitor positioning via homepage + one strategic subpage hop."""
    root = _normalize_root(domain)
    signals: list[SignalReference] = []

    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
        try:
            response = await client.get(root)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

            hero = soup.find("h1")
            if hero:
                hero_text = hero.get_text(" ", strip=True)
                if hero_text:
                    signals.append(
                        _make_signal(
                            source=domain,
                            source_url=root,
                            content=f"{domain} hero: {hero_text[:220]}",
                            raw_quote=hero_text[:220],
                            confidence=0.9,
                        )
                    )

            next_url: str | None = None
            for link in soup.find_all("a", href=True):
                href = str(link["href"]).strip()
                if not href or href.startswith("#"):
                    continue
                if _link_matches(href):
                    next_url = href if href.startswith("http") else urljoin(root + "/", href.lstrip("/"))
                    break

            if next_url:
                try:
                    response_2 = await client.get(next_url)
                    response_2.raise_for_status()
                    soup_2 = BeautifulSoup(response_2.text, "html.parser")

                    for para in _extract_competitor_paragraphs(soup_2):
                        signals.append(
                            _make_signal(
                                source=domain,
                                source_url=next_url,
                                content=para,
                                raw_quote=para,
                                confidence=0.75,
                            )
                        )
                except Exception:
                    # Non-fatal; homepage signal still remains useful.
                    pass
        except Exception:
            # Non-fatal; search snippets can still provide useful external context.
            pass

        if len(signals) < 2:
            try:
                signals.extend(await _duckduckgo_competitor_snippets(client, domain))
            except Exception:
                pass

    if len(signals) < 3:
        try:
            signals.extend(await _serpapi_competitor_snippets(domain))
        except Exception:
            pass

    return signals


async def scrape_competitors(domains: list[str] | None = None) -> list[SignalReference]:
    """Scrape all configured competitor domains and merge extracted signals."""
    targets = domains or TARGETS
    collected: list[SignalReference] = []

    for domain in targets:
        try:
            collected.extend(await scrape_competitor(domain))
        except Exception:
            continue

    return collected
