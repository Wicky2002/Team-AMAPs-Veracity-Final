from __future__ import annotations

import hashlib
import math
import re
from functools import lru_cache

PROTOTYPES: dict[str, str] = {
    "research": "competitor positioning gap market signals trends",
    "generate": "write outreach content create email sequence",
    "ab": "different angle version rewrite variation test",
    "feedback": "reply rate performed resonated got results clicked",
}


@lru_cache(maxsize=1)
def _load_sentence_transformer():
    """Lazy-load to keep startup fast and allow fallback when dependency/model is missing."""
    try:
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer("all-MiniLM-L6-v2")
    except Exception:
        return None


def _normalize(v: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _hash_embedding(text: str, dims: int = 256) -> list[float]:
    vec = [0.0] * dims
    tokens = re.findall(r"[a-zA-Z0-9_]+", text.lower())
    for token in tokens:
        digest = hashlib.md5(token.encode("utf-8")).hexdigest()
        idx = int(digest[:8], 16) % dims
        sign = -1.0 if int(digest[-1], 16) % 2 else 1.0
        vec[idx] += sign
    return _normalize(vec)


def _embed(text: str) -> list[float]:
    model = _load_sentence_transformer()
    if model is not None:
        try:
            arr = model.encode(text)
            return _normalize([float(x) for x in arr])
        except Exception:
            pass
    return _hash_embedding(text)


def detect_intent(message: str, current_stage: str) -> str:
    """Semantic-ish intent detection with robust fallback.

    Uses sentence-transformers when available; otherwise hashed embeddings.
    """
    cleaned = (message or "").strip()
    if not cleaned:
        return current_stage

    msg_emb = _embed(cleaned)
    scores = {intent: _dot(msg_emb, _embed(proto)) for intent, proto in PROTOTYPES.items()}

    best_intent = max(scores, key=scores.get)
    best_score = scores[best_intent]

    # Keep stage stable when confidence is too weak.
    if best_score < 0.15 and current_stage in PROTOTYPES:
        return current_stage
    return best_intent
