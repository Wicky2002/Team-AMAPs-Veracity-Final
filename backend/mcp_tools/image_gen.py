"""Free, keyless image generation for outreach variants via Pollinations.ai.

Pollinations serves generated images directly from a GET URL, so no server-side
fetch/proxy is needed here -- the URL itself is embeddable as an <img src>.
A stable seed (derived from the prompt) keeps the same variant showing the
same image across re-renders instead of regenerating on every load.
"""

from __future__ import annotations

import hashlib
from urllib.parse import quote

POLLINATIONS_BASE_URL = "https://image.pollinations.ai/prompt"

_STYLE_SUFFIX = (
    "professional B2B SaaS product advertisement photography, clean modern UI dashboard "
    "mockup on a laptop or phone screen, polished marketing creative, studio lighting, "
    "vibrant brand accent colors, high production value social media ad campaign visual, "
    "no readable text, no words, no letters, no logos"
)


def _stable_seed(text: str) -> int:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def build_variant_image_prompt(*, angle: str, hook: str) -> str:
    clipped_hook = (hook or "").strip()[:160]
    angle_label = (angle or "campaign").replace("_", " ")
    return f"{angle_label} concept: {clipped_hook}. {_STYLE_SUFFIX}"


def generate_variant_image_url(*, angle: str, hook: str, width: int = 1024, height: int = 576) -> str:
    prompt = build_variant_image_prompt(angle=angle, hook=hook)
    seed = _stable_seed(prompt)
    encoded_prompt = quote(prompt, safe="")
    return (
        f"{POLLINATIONS_BASE_URL}/{encoded_prompt}"
        f"?width={width}&height={height}&seed={seed}&nologo=true"
    )
