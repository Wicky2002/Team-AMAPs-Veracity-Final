"""Real posting + feedback ingestion channel via a Discord bot.

Uses the bot's REST API directly (no gateway connection needed) to post a
variant as a message and later read back real reaction counts as engagement
signal for the feedback loop.
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any

import httpx

DISCORD_API_BASE = "https://discord.com/api/v10"


def _parse_data_uri(image_url: str) -> tuple[bytes, str] | None:
    """Decode a data: URI into (raw_bytes, filename). Returns None if it
    doesn't parse as one -- caller falls back to treating it as a plain URL."""
    if not image_url.startswith("data:"):
        return None
    try:
        header, encoded = image_url.split(",", 1)
        mime_type = header[len("data:") :].split(";")[0] or "image/png"
        extension = mime_type.split("/")[-1] or "png"
        return base64.b64decode(encoded), f"variant.{extension}"
    except Exception:
        return None


class DiscordNotConfigured(Exception):
    """Raised when DISCORD_BOT_TOKEN / DISCORD_CHANNEL_ID are missing."""


def _auth_headers() -> dict[str, str]:
    token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
    if not token:
        raise DiscordNotConfigured("DISCORD_BOT_TOKEN is not set")
    return {"Authorization": f"Bot {token}"}


def _channel_id() -> str:
    channel_id = os.getenv("DISCORD_CHANNEL_ID", "").strip()
    if not channel_id:
        raise DiscordNotConfigured("DISCORD_CHANNEL_ID is not set")
    return channel_id


async def post_variant_message(*, label: str, content: str, image_url: str | None) -> dict[str, Any]:
    """Post a variant to the configured Discord channel. Returns the created
    message JSON. A data: URI (e.g. from Gemini) is uploaded as a real file
    attachment -- Discord's embed.image.url is fetched server-side and can't
    resolve a data: URI, only an http(s) one (e.g. Pollinations)."""
    channel_id = _channel_id()
    embed: dict[str, Any] = {"title": label, "description": content[:4000]}

    decoded = _parse_data_uri(image_url) if image_url else None

    async with httpx.AsyncClient(timeout=30) as client:
        if decoded:
            raw_bytes, filename = decoded
            embed["image"] = {"url": f"attachment://{filename}"}
            # Discord requires each uploaded file to be explicitly declared in
            # an `attachments` array (id matching the files[N] index) -- the
            # multipart part alone isn't enough for it to attach the file.
            payload = {
                "embeds": [embed],
                "attachments": [{"id": 0, "filename": filename}],
            }
            response = await client.post(
                f"{DISCORD_API_BASE}/channels/{channel_id}/messages",
                headers=_auth_headers(),
                data={"payload_json": json.dumps(payload)},
                files={"files[0]": (filename, raw_bytes, "image/png")},
            )
        else:
            if image_url:
                embed["image"] = {"url": image_url}
            response = await client.post(
                f"{DISCORD_API_BASE}/channels/{channel_id}/messages",
                headers=_auth_headers(),
                json={"embeds": [embed]},
            )
        response.raise_for_status()
        return response.json()


async def get_message_reaction_counts(*, message_id: str) -> dict[str, int]:
    """Return {emoji: count} for all reactions currently on the message."""
    channel_id = _channel_id()

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            f"{DISCORD_API_BASE}/channels/{channel_id}/messages/{message_id}",
            headers=_auth_headers(),
        )
        response.raise_for_status()
        message = response.json()

    counts: dict[str, int] = {}
    for reaction in message.get("reactions", []) or []:
        emoji = reaction.get("emoji", {})
        key = emoji.get("name") or emoji.get("id") or "unknown"
        counts[key] = int(reaction.get("count", 0))
    return counts
