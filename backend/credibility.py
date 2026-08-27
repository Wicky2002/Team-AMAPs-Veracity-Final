"""Domain-level credibility scoring, layered on top of the existing
per-category source-quality prior in graph_nodes.py.

Two signals in the same category (e.g. both "pestel") can come from very
different quality sources -- an established outlet vs. an anonymous blog --
and the plain category prior can't tell them apart. This adds a real,
per-domain weighting: known credible sources score higher, everything
unrecognized stays neutral (never unfairly penalized just for being
unlisted), matching the "weight the source, then weight the final analysis
accordingly" idea directly.
"""

from __future__ import annotations

from urllib.parse import urlparse

# Established news, data, and analyst sources -- highest tier.
_HIGH_CREDIBILITY_DOMAINS = {
    "reuters.com",
    "bloomberg.com",
    "wsj.com",
    "ft.com",
    "techcrunch.com",
    "forbes.com",
    "businessinsider.com",
    "cnbc.com",
    "theguardian.com",
    "bbc.com",
    "bbc.co.uk",
    "nytimes.com",
    "economist.com",
    "statista.com",
    "gartner.com",
    "mckinsey.com",
    "hbr.org",
    "trends.google.com",
    "news.google.com",
}

# Community/social sources -- real signal, lower editorial authority.
_MID_CREDIBILITY_DOMAINS = {
    "reddit.com",
    "quora.com",
    "producthunt.com",
    "news.ycombinator.com",
}

_HIGH_TIER_MULTIPLIER = 1.15
_MID_TIER_MULTIPLIER = 0.9
_NEUTRAL_MULTIPLIER = 1.0


def _root_domain(url: str) -> str | None:
    try:
        netloc = urlparse(url).netloc.lower()
    except Exception:
        return None
    return netloc.removeprefix("www.") or None


def _matches_any(domain: str, known: set[str]) -> bool:
    return any(domain == d or domain.endswith(f".{d}") for d in known)


def credibility_tier(source_url: str | None) -> str:
    """Human-readable tier for UI display: 'high' | 'mid' | 'unverified'."""
    if not source_url:
        return "unverified"
    domain = _root_domain(source_url)
    if not domain:
        return "unverified"
    if _matches_any(domain, _HIGH_CREDIBILITY_DOMAINS):
        return "high"
    if _matches_any(domain, _MID_CREDIBILITY_DOMAINS):
        return "mid"
    return "unverified"


def domain_credibility_multiplier(source_url: str | None) -> float:
    """Multiplier applied on top of the per-category source-quality prior."""
    tier = credibility_tier(source_url)
    if tier == "high":
        return _HIGH_TIER_MULTIPLIER
    if tier == "mid":
        return _MID_TIER_MULTIPLIER
    return _NEUTRAL_MULTIPLIER
