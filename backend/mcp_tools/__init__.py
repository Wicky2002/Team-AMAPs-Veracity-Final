"""MCP tool implementations for live signal ingestion."""

from .audience_intel import scan_audience_intent, scan_hot_posts
from .competitor_intel import TARGETS, scrape_competitor, scrape_competitors
from .pestel_scan import get_last_pestel_error, scan_pestel_trends

__all__ = [
    "TARGETS",
    "scan_audience_intent",
    "scan_hot_posts",
    "scan_pestel_trends",
    "get_last_pestel_error",
    "scrape_competitor",
    "scrape_competitors",
]
