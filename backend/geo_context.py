from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class GeoContext:
    country_name: str
    iso2: str
    aliases: tuple[str, ...]
    city_hints: tuple[str, ...]
    subreddit_hints: tuple[str, ...]
    search_hints: tuple[str, ...]


_GEO_CONTEXTS: tuple[GeoContext, ...] = (
    GeoContext(
        country_name="Sri Lanka",
        iso2="LK",
        aliases=("sri lanka", "srilanka", "lankan"),
        city_hints=("colombo", "kandy", "galle"),
        subreddit_hints=("srilanka",),
        search_hints=("sri lanka", "colombo"),
    ),
    GeoContext(
        country_name="India",
        iso2="IN",
        aliases=("india", "indian", "bharat"),
        city_hints=("bangalore", "bengaluru", "mumbai", "delhi", "hyderabad", "chennai", "pune"),
        subreddit_hints=("india",),
        search_hints=("india", "indian b2b"),
    ),
    GeoContext(
        country_name="United Arab Emirates",
        iso2="AE",
        aliases=("uae", "united arab emirates", "emirati"),
        city_hints=("dubai", "abu dhabi", "sharjah"),
        subreddit_hints=("dubai",),
        search_hints=("uae", "dubai"),
    ),
    GeoContext(
        country_name="Singapore",
        iso2="SG",
        aliases=("singapore", "singaporean"),
        city_hints=("singapore"),
        subreddit_hints=("singapore",),
        search_hints=("singapore",),
    ),
    GeoContext(
        country_name="Malaysia",
        iso2="MY",
        aliases=("malaysia", "malaysian"),
        city_hints=("kuala lumpur", "kl"),
        subreddit_hints=("malaysia",),
        search_hints=("malaysia",),
    ),
    GeoContext(
        country_name="Indonesia",
        iso2="ID",
        aliases=("indonesia", "indonesian"),
        city_hints=("jakarta",),
        subreddit_hints=("indonesia",),
        search_hints=("indonesia",),
    ),
    GeoContext(
        country_name="Philippines",
        iso2="PH",
        aliases=("philippines", "philippine", "filipino"),
        city_hints=("manila",),
        subreddit_hints=("philippines",),
        search_hints=("philippines",),
    ),
    GeoContext(
        country_name="Vietnam",
        iso2="VN",
        aliases=("vietnam", "vietnamese"),
        city_hints=("ho chi minh", "hanoi"),
        subreddit_hints=("vietnam",),
        search_hints=("vietnam",),
    ),
    GeoContext(
        country_name="Thailand",
        iso2="TH",
        aliases=("thailand", "thai"),
        city_hints=("bangkok",),
        subreddit_hints=("thailand",),
        search_hints=("thailand",),
    ),
)


def _contains_alias(text: str, alias: str) -> bool:
    escaped = re.escape(alias.strip().lower())
    pattern = escaped.replace(r"\ ", r"\s+")
    return re.search(rf"\b{pattern}\b", text) is not None


def detect_geo_context(text: str) -> GeoContext | None:
    normalized = (text or "").lower()
    if not normalized.strip():
        return None

    for context in _GEO_CONTEXTS:
        for alias in context.aliases:
            if _contains_alias(normalized, alias):
                return context
    return None


def build_topic_query_variants(topic: str, max_queries: int = 6) -> list[str]:
    normalized = (topic or "AI SDR").strip() or "AI SDR"
    geo = detect_geo_context(normalized)

    variants: list[str] = [normalized]

    if geo is not None:
        normalized_lower = normalized.lower()
        if geo.country_name.lower() not in normalized_lower:
            variants.append(f"{normalized} {geo.country_name}")

        variants.extend(
            [
                f"AI SDR {geo.country_name}",
                f"B2B sales {geo.country_name}",
            ]
        )

        for city in geo.city_hints[:2]:
            variants.append(f"{normalized} {city}")

    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in variants:
        cleaned = candidate.strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(cleaned)

    return deduped[:max_queries]


def get_geo_subreddit_hints(topic: str) -> tuple[str, ...]:
    geo = detect_geo_context(topic)
    if geo is None:
        return tuple()
    return geo.subreddit_hints


def get_serpapi_geo_params(topic: str) -> dict[str, str]:
    geo = detect_geo_context(topic)
    if geo is None:
        return {}

    return {
        "geo": geo.iso2,
        "gl": geo.iso2.lower(),
        "hl": "en",
    }


def get_geo_terms(topic: str) -> tuple[str, ...]:
    geo = detect_geo_context(topic)
    if geo is None:
        return tuple()

    terms = {
        geo.country_name.lower(),
        geo.iso2.lower(),
        *[alias.lower() for alias in geo.aliases],
        *[city.lower() for city in geo.city_hints],
        *[hint.lower() for hint in geo.search_hints],
    }

    return tuple(sorted(term for term in terms if term))
