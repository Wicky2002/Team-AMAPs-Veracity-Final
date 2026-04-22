from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx

from state import SignalReference

REMOTIVE_JOBS_ENDPOINT = "https://remotive.com/api/remote-jobs"
SERP_API_ENDPOINT = "https://serpapi.com/search.json"
DEFAULT_TIMEOUT_SECONDS = 10.0


def _headers() -> dict[str, str]:
    user_agent = os.getenv("JOB_SIGNALS_USER_AGENT", "Veracity/1.0 (hackathon research bot)").strip()
    return {
        "User-Agent": user_agent or "Veracity/1.0 (hackathon research bot)",
        "Accept": "application/json",
    }


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


async def _scan_remotive_jobs(topic: str, limit: int = 6) -> list[SignalReference]:
    query = (topic or "AI SDR").strip() or "AI SDR"

    async with httpx.AsyncClient(
        headers=_headers(),
        timeout=DEFAULT_TIMEOUT_SECONDS,
        follow_redirects=True,
    ) as client:
        response = await client.get(REMOTIVE_JOBS_ENDPOINT, params={"search": query})
        response.raise_for_status()
        payload = response.json()

    if not isinstance(payload, dict):
        return []

    jobs = payload.get("jobs")
    if not isinstance(jobs, list):
        return []

    signals: list[SignalReference] = []
    for job in jobs[: max(1, min(limit, 10))]:
        if not isinstance(job, dict):
            continue

        company = str(job.get("company_name", "")).strip() or "Unknown company"
        title = str(job.get("title", "")).strip()
        category = str(job.get("category", "")).strip()
        if not title:
            continue

        summary = f"{company} hiring {title}" + (f" in {category}" if category else "")
        source_url = str(job.get("url", "")).strip() or "https://remotive.com/"

        signals.append(
            SignalReference(
                source_type="audience",
                source="job_market:remotive",
                source_url=source_url,
                content=summary[:220],
                quote=summary[:220],
                raw_quote=summary[:220],
                confidence=0.62,
            )
        )

    return _dedupe_signals(signals)


async def _scan_serpapi_google_jobs(topic: str, limit: int = 6) -> list[SignalReference]:
    api_key = os.getenv("SERP_API_KEY", "").strip()
    if not api_key:
        return []

    query = (topic or "AI SDR").strip() or "AI SDR"
    params = {
        "engine": "google_jobs",
        "q": query,
        "api_key": api_key,
    }

    async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
        response = await client.get(SERP_API_ENDPOINT, params=params)
        response.raise_for_status()
        payload = response.json()

    if not isinstance(payload, dict):
        return []

    jobs = payload.get("jobs_results")
    if not isinstance(jobs, list):
        return []

    signals: list[SignalReference] = []
    for job in jobs[: max(1, min(limit, 10))]:
        if not isinstance(job, dict):
            continue

        title = str(job.get("title", "")).strip()
        company = str(job.get("company_name", "")).strip() or "Unknown company"
        location = str(job.get("location", "")).strip()
        if not title:
            continue

        summary = f"{company} hiring {title}" + (f" in {location}" if location else "")
        source_url = str(job.get("related_links", [{}])[0].get("link", "")).strip() if isinstance(job.get("related_links"), list) else ""
        if not source_url:
            source_url = "https://www.google.com/search?q=google+jobs"

        signals.append(
            SignalReference(
                source_type="audience",
                source="job_market:google_jobs",
                source_url=source_url,
                content=summary[:220],
                quote=summary[:220],
                raw_quote=summary[:220],
                confidence=0.65,
            )
        )

    return _dedupe_signals(signals)


async def scan_job_market_signals(topic: str, limit: int = 6) -> list[SignalReference]:
    tasks = [
        _scan_remotive_jobs(topic, limit=limit),
        _scan_serpapi_google_jobs(topic, limit=limit),
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)
    merged: list[SignalReference] = []
    for result in results:
        if isinstance(result, Exception):
            continue
        merged.extend(result)

    return _dedupe_signals(merged)
