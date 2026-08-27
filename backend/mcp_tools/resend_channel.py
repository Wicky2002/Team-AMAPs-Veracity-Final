"""Real email outreach channel via Resend's REST API.

Uses plain HTTP (POST /emails) to send a variant as a real email, and polls
GET /emails/{id} for delivery/open/click status -- a pull model, same shape
as how Discord reactions are polled, since Resend's push-based webhooks need
a publicly reachable URL a local dev backend doesn't have without deploying.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

RESEND_API_BASE = "https://api.resend.com"


class ResendNotConfigured(Exception):
    """Raised when RESEND_API_KEY / a recipient is missing."""


def _auth_headers() -> dict[str, str]:
    key = os.getenv("RESEND_API_KEY", "").strip()
    if not key:
        raise ResendNotConfigured("RESEND_API_KEY is not set")
    return {"Authorization": f"Bearer {key}"}


def _from_address() -> str:
    # Resend's shared sandbox sender -- works immediately with no domain
    # verification, but can only deliver to the account's verified test
    # recipient(s) until a real sending domain is verified.
    return os.getenv("RESEND_FROM_ADDRESS", "onboarding@resend.dev").strip() or "onboarding@resend.dev"


def _test_recipient() -> str:
    to = os.getenv("RESEND_TEST_RECIPIENT", "").strip()
    if not to:
        raise ResendNotConfigured("RESEND_TEST_RECIPIENT is not set")
    return to


def _variant_email_html(*, label: str, subject_line: str, hook: str, cta: str, image_url: str | None) -> str:
    # data: URIs (our OpenAI-generated images) are blocked by most email
    # clients' HTML sanitizers -- only include the image if it's a real
    # hosted http(s) URL (e.g. the Pollinations fallback path).
    image_html = ""
    if image_url and image_url.startswith("http"):
        image_html = f'<img src="{image_url}" alt="" style="max-width:480px;border-radius:8px;margin-top:12px;" />'

    return f"""
    <div style="font-family: sans-serif; max-width: 560px;">
      <p style="text-transform:uppercase;font-size:12px;color:#6366f1;font-weight:700;">{label}</p>
      <h2 style="margin:4px 0 12px;">{subject_line}</h2>
      <p style="color:#334155;line-height:1.5;">{hook}</p>
      <p style="margin-top:16px;"><strong>CTA:</strong> {cta}</p>
      {image_html}
    </div>
    """


async def send_variant_email(
    *, label: str, subject_line: str, hook: str, cta: str, image_url: str | None
) -> dict[str, Any]:
    """Send one variant as a real email. Returns the Resend API response
    (includes the email id, needed later to poll delivery/open status)."""
    headers = _auth_headers()
    to_address = _test_recipient()
    html = _variant_email_html(label=label, subject_line=subject_line, hook=hook, cta=cta, image_url=image_url)

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            f"{RESEND_API_BASE}/emails",
            headers=headers,
            json={
                "from": _from_address(),
                "to": [to_address],
                "subject": f"[{label}] {subject_line}",
                "html": html,
            },
        )
        response.raise_for_status()
        return response.json()


async def get_email_status(email_id: str) -> dict[str, Any]:
    """Poll Resend for one email's current status/event history."""
    headers = _auth_headers()
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(f"{RESEND_API_BASE}/emails/{email_id}", headers=headers)
        response.raise_for_status()
        return response.json()
