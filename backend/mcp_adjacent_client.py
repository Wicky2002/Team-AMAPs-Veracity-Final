"""Real MCP client: spawns mcp_server_adjacent.py as a subprocess over stdio
and calls its tools via the Model Context Protocol (initialize -> call_tool),
not a direct Python function call. Converts tool results into SignalReference
entries for the "adjacent" and "temporal" signal categories.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from state import SignalReference

_SERVER_SCRIPT = str(Path(__file__).resolve().parent / "mcp_server_adjacent.py")


def _server_params() -> StdioServerParameters:
    return StdioServerParameters(command=sys.executable, args=[_SERVER_SCRIPT])


def _extract_payload(result: Any) -> Any:
    structured = getattr(result, "structured_content", None)
    if structured is not None:
        return structured

    content = getattr(result, "content", None) or []
    for block in content:
        text = getattr(block, "text", None)
        if isinstance(text, str) and text.strip():
            try:
                return json.loads(text)
            except Exception:
                continue
    return None


async def _call_tool(tool_name: str, arguments: dict[str, Any]) -> Any:
    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            if getattr(result, "is_error", False):
                raise RuntimeError(f"MCP tool {tool_name} returned an error result")
            return _extract_payload(result)


async def scan_adjacent_via_mcp(topic: str) -> list[SignalReference]:
    try:
        payload = await _call_tool("scan_adjacent_signals", {"topic": topic})
    except Exception:
        return []

    items = payload if isinstance(payload, list) else (payload or {}).get("result") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return []

    signals: list[SignalReference] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        snippet = str(item.get("snippet", "")).strip()
        if not snippet:
            continue
        url = str(item.get("url", "")).strip() or None
        signals.append(
            SignalReference(
                source_type="adjacent",
                source="adjacent_web_scan",
                source_url=url,
                content=snippet,
                quote=snippet,
                raw_quote=snippet,
                confidence=0.6,
            )
        )
    return signals


async def get_temporal_signal_via_mcp() -> SignalReference | None:
    try:
        payload = await _call_tool("get_temporal_context", {})
    except Exception:
        return None

    if not isinstance(payload, dict):
        return None

    quarter = str(payload.get("quarter", "")).strip()
    seasonal_note = str(payload.get("seasonal_note", "")).strip()
    day = str(payload.get("day_of_week", "")).strip()
    parts = [p for p in [quarter, day, seasonal_note] if p]
    text = ": ".join([", ".join(parts[:2]), parts[2]]) if len(parts) >= 3 else " ".join(parts)
    if not text.strip():
        return None

    return SignalReference(
        source_type="temporal",
        source="calendar_context",
        source_url=None,
        content=text,
        quote=text,
        raw_quote=text,
        confidence=0.8,
    )
