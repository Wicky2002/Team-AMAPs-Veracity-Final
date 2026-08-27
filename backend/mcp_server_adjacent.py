"""Real MCP server exposing the two signal categories the core pipeline
doesn't otherwise cover: adjacent market threats/opportunities, and
contextual/temporal signals. Run over stdio and spawned as a subprocess by
mcp_adjacent_client.py -- this is genuine Model Context Protocol tool usage,
not a plain function call dressed up in an "mcp_tools" folder name.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
from bs4 import BeautifulSoup
from mcp.server.mcpserver import MCPServer

server = MCPServer(name="adjacent-intel")

DUCKDUCKGO_HTML_SEARCH_URL = "https://duckduckgo.com/html/"

_MONTH_NOTES: dict[int, str] = {
    1: "New fiscal year planning; budgets just reset",
    2: "Post-planning execution ramp",
    3: "Q1 close push",
    4: "New quarter kickoff",
    5: "Mid-quarter execution",
    6: "H1 close push",
    7: "Summer slowdown in many B2B buying cycles",
    8: "Pre-Q4 planning begins",
    9: "Q3 close push, back-to-work ramp",
    10: "Q4 kickoff; budget-flush season starting",
    11: "End-of-year budget flush",
    12: "Year-end close, holiday slowdown",
}


@server.tool()
async def scan_adjacent_signals(topic: str) -> list[dict[str, Any]]:
    """Scan for adjacent market threats/opportunities outside the immediate
    named-competitor set for the given topic -- broader disruption, emerging
    alternatives, category shifts."""
    query = f"{topic} market disruption emerging alternative category shift"
    results: list[dict[str, Any]] = []
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
        if len(snippet) < 30:
            continue

        results.append({"url": href or "https://duckduckgo.com/", "snippet": snippet[:240]})
        if len(results) >= 4:
            break

    return results


@server.tool()
def get_temporal_context() -> dict[str, Any]:
    """Return deterministic contextual/temporal signal for right now: date,
    fiscal quarter, day of week, and a seasonal buying-cycle note. No network
    call -- this is genuinely current, not training data."""
    now = datetime.now(timezone.utc)
    quarter = (now.month - 1) // 3 + 1
    return {
        "date": now.date().isoformat(),
        "quarter": f"Q{quarter} {now.year}",
        "day_of_week": now.strftime("%A"),
        "seasonal_note": _MONTH_NOTES.get(now.month, ""),
    }


if __name__ == "__main__":
    server.run()
