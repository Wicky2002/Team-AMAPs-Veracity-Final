from __future__ import annotations

import asyncio
import json
import os
from typing import Any

try:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg.types.json import Json
except Exception:  # pragma: no cover - optional dependency guard
    psycopg = None
    dict_row = None
    Json = None

from state import OutreachVariant, SignalReference
from intent_router import embed_text_for_memory

_SCHEMA_STATEMENTS: tuple[str, ...] = (
    "CREATE EXTENSION IF NOT EXISTS pgcrypto",
    """
    CREATE TABLE IF NOT EXISTS signal_cache (
        id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
        domain TEXT NOT NULL,
        topic TEXT NOT NULL,
        signals JSONB NOT NULL,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        expires_at TIMESTAMPTZ DEFAULT NOW() + INTERVAL '2 hours'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ab_results (
        id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
        thread_id TEXT NOT NULL,
        cycle_n INTEGER NOT NULL,
        variant_id TEXT NOT NULL,
        hypothesis TEXT,
        open_rate FLOAT,
        reply_rate FLOAT,
        ctr FLOAT,
        created_at TIMESTAMPTZ DEFAULT NOW()
    )
    """,
)

_VECTOR_MEMORY_SCHEMA_STATEMENTS: tuple[str, ...] = (
    "CREATE EXTENSION IF NOT EXISTS vector",
    """
    CREATE TABLE IF NOT EXISTS response_memory (
        id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
        thread_id TEXT NOT NULL,
        cycle_n INTEGER NOT NULL,
        prompt TEXT NOT NULL,
        top_signal TEXT NOT NULL,
        winning_variant TEXT NOT NULL,
        winning_angle TEXT NOT NULL,
        open_rate FLOAT NOT NULL,
        reply_rate FLOAT NOT NULL,
        click_rate FLOAT NOT NULL,
        feedback_note TEXT,
        summary TEXT NOT NULL,
        embedding VECTOR(384) NOT NULL,
        created_at TIMESTAMPTZ DEFAULT NOW()
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_response_memory_created_at
    ON response_memory (created_at DESC)
    """,
)

_tables_ready = False
_tables_lock = asyncio.Lock()
_vector_memory_ready = False
_vector_memory_lock = asyncio.Lock()


def _conn_string() -> str | None:
    value = os.getenv("SUPABASE_POSTGRES_URL", "").strip()
    return value or None


async def _connect() -> psycopg.AsyncConnection[Any] | None:
    if psycopg is None:
        return None

    conn_str = _conn_string()
    if not conn_str:
        return None

    try:
        return await psycopg.AsyncConnection.connect(conn_str, autocommit=True)
    except Exception:
        return None


async def ensure_phase3_tables() -> bool:
    global _tables_ready

    if _tables_ready:
        return True

    if psycopg is None:
        return False

    if _conn_string() is None:
        return False

    async with _tables_lock:
        if _tables_ready:
            return True

        conn = await _connect()
        if conn is None:
            return False

        try:
            async with conn.cursor() as cur:
                for stmt in _SCHEMA_STATEMENTS:
                    await cur.execute(stmt)
            _tables_ready = True
            return True
        except Exception:
            return False
        finally:
            await conn.close()


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{float(value):.8f}" for value in values) + "]"


def _memory_summary(
    *,
    winning_angle: str,
    winning_variant: str,
    top_signal: str,
    reply_rate: float,
    open_rate: float,
    feedback_note: str | None,
) -> str:
    note = (feedback_note or "").strip()
    base = (
        f"Angle={winning_angle}; Winner={winning_variant}; "
        f"Reply={reply_rate * 100:.1f}%; Open={open_rate * 100:.1f}%; "
        f"TopSignal={top_signal}"
    )
    if not note:
        return base
    return f"{base}; Note={note[:220]}"


async def ensure_vector_memory_table() -> bool:
    global _vector_memory_ready

    if _vector_memory_ready:
        return True

    if psycopg is None:
        return False

    if _conn_string() is None:
        return False

    async with _vector_memory_lock:
        if _vector_memory_ready:
            return True

        conn = await _connect()
        if conn is None:
            return False

        try:
            async with conn.cursor() as cur:
                for stmt in _VECTOR_MEMORY_SCHEMA_STATEMENTS:
                    await cur.execute(stmt)
            _vector_memory_ready = True
            return True
        except Exception:
            return False
        finally:
            await conn.close()


async def load_signal_cache(domain: str, topic: str) -> list[SignalReference] | None:
    if not await ensure_phase3_tables():
        return None

    conn = await _connect()
    if conn is None:
        return None

    try:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT signals
                FROM signal_cache
                WHERE domain = %s
                  AND topic = %s
                  AND expires_at > NOW()
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (domain, topic),
            )
            row = await cur.fetchone()

        if not row:
            return None

        payload = row.get("signals")
        if isinstance(payload, str):
            payload = json.loads(payload)

        if not isinstance(payload, list):
            return None

        signals: list[SignalReference] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            try:
                signals.append(SignalReference.model_validate(item))
            except Exception:
                continue
        return signals or None
    except Exception:
        return None
    finally:
        await conn.close()


async def save_signal_cache(domain: str, topic: str, signals: list[SignalReference]) -> None:
    if not signals:
        return

    if Json is None:
        return

    if not await ensure_phase3_tables():
        return

    conn = await _connect()
    if conn is None:
        return

    try:
        payload = [signal.model_dump() for signal in signals]
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO signal_cache (domain, topic, signals)
                VALUES (%s, %s, %s)
                """,
                (domain, topic, Json(payload)),
            )
    except Exception:
        return
    finally:
        await conn.close()


def _variant_label(index: int) -> str:
    return f"Variant {chr(65 + max(index, 0))}"


async def save_ab_results(
    *,
    thread_id: str,
    cycle_n: int,
    variants: list[OutreachVariant],
    metrics: list[dict[str, Any]],
) -> None:
    if not metrics:
        return

    if not await ensure_phase3_tables():
        return

    conn = await _connect()
    if conn is None:
        return

    try:
        async with conn.cursor() as cur:
            for metric in metrics:
                try:
                    idx = int(metric.get("variant", 0))
                except Exception:
                    idx = 0

                hypothesis = variants[idx].hypothesis if 0 <= idx < len(variants) else None

                await cur.execute(
                    """
                    INSERT INTO ab_results (thread_id, cycle_n, variant_id, hypothesis, open_rate, reply_rate, ctr)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        thread_id,
                        cycle_n,
                        _variant_label(idx),
                        hypothesis,
                        float(metric.get("open_rate", 0.0)),
                        float(metric.get("reply_rate", 0.0)),
                        float(metric.get("click_rate", metric.get("ctr", 0.0))),
                    ),
                )
    except Exception:
        return
    finally:
        await conn.close()


def _variant_index_from_label(label: str, fallback: int) -> int:
    if not label:
        return fallback

    cleaned = label.strip().upper()
    if cleaned.startswith("VARIANT ") and len(cleaned) >= 9:
        letter = cleaned[-1]
        if "A" <= letter <= "Z":
            return ord(letter) - ord("A")
    return fallback


async def load_ab_results(thread_id: str, cycle_n: int) -> list[dict[str, Any]] | None:
    if not await ensure_phase3_tables():
        return None

    conn = await _connect()
    if conn is None:
        return None

    try:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT variant_id, open_rate, reply_rate, ctr
                FROM ab_results
                WHERE thread_id = %s
                  AND cycle_n = %s
                ORDER BY created_at ASC
                """,
                (thread_id, cycle_n),
            )
            rows = await cur.fetchall()

        if not rows:
            return None

        metrics: list[dict[str, Any]] = []
        for idx, row in enumerate(rows):
            variant_id = str(row.get("variant_id", ""))
            metrics.append(
                {
                    "variant": _variant_index_from_label(variant_id, idx),
                    "open_rate": float(row.get("open_rate") or 0.0),
                    "reply_rate": float(row.get("reply_rate") or 0.0),
                    "click_rate": float(row.get("ctr") or 0.0),
                }
            )
        return metrics
    except Exception:
        return None
    finally:
        await conn.close()


async def save_response_memory(
    *,
    thread_id: str,
    cycle_n: int,
    prompt: str,
    top_signal: str,
    winning_variant: str,
    winning_angle: str,
    open_rate: float,
    reply_rate: float,
    click_rate: float,
    feedback_note: str | None = None,
) -> None:
    prompt_text = (prompt or "").strip()
    if not prompt_text:
        return

    if not await ensure_vector_memory_table():
        return

    conn = await _connect()
    if conn is None:
        return

    summary = _memory_summary(
        winning_angle=winning_angle,
        winning_variant=winning_variant,
        top_signal=top_signal,
        reply_rate=reply_rate,
        open_rate=open_rate,
        feedback_note=feedback_note,
    )
    embedding = embed_text_for_memory(prompt_text)
    embedding_literal = _vector_literal(embedding)

    try:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO response_memory (
                    thread_id, cycle_n, prompt, top_signal,
                    winning_variant, winning_angle,
                    open_rate, reply_rate, click_rate,
                    feedback_note, summary, embedding
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector)
                """,
                (
                    thread_id,
                    cycle_n,
                    prompt_text,
                    top_signal,
                    winning_variant,
                    winning_angle,
                    float(open_rate),
                    float(reply_rate),
                    float(click_rate),
                    feedback_note,
                    summary,
                    embedding_literal,
                ),
            )
    except Exception:
        return
    finally:
        await conn.close()


async def search_response_memories(*, query: str, limit: int = 3) -> list[dict[str, Any]]:
    query_text = (query or "").strip()
    if not query_text:
        return []

    if limit < 1:
        return []

    if not await ensure_vector_memory_table():
        return []

    conn = await _connect()
    if conn is None:
        return []

    embedding_literal = _vector_literal(embed_text_for_memory(query_text))

    try:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT
                    thread_id,
                    cycle_n,
                    prompt,
                    top_signal,
                    winning_variant,
                    winning_angle,
                    open_rate,
                    reply_rate,
                    click_rate,
                    feedback_note,
                    summary,
                    created_at,
                    (1 - (embedding <=> %s::vector)) AS similarity
                FROM response_memory
                ORDER BY embedding <=> %s::vector, created_at DESC
                LIMIT %s
                """,
                (embedding_literal, embedding_literal, int(limit)),
            )
            rows = await cur.fetchall()
    except Exception:
        return []
    finally:
        await conn.close()

    memories: list[dict[str, Any]] = []
    for row in rows:
        memories.append(
            {
                "thread_id": str(row.get("thread_id", "")),
                "cycle_n": int(row.get("cycle_n") or 0),
                "prompt": str(row.get("prompt", "")),
                "top_signal": str(row.get("top_signal", "")),
                "winning_variant": str(row.get("winning_variant", "")),
                "winning_angle": str(row.get("winning_angle", "")),
                "open_rate": float(row.get("open_rate") or 0.0),
                "reply_rate": float(row.get("reply_rate") or 0.0),
                "click_rate": float(row.get("click_rate") or 0.0),
                "feedback_note": str(row.get("feedback_note") or ""),
                "summary": str(row.get("summary", "")),
                "created_at": str(row.get("created_at") or ""),
                "similarity": float(row.get("similarity") or 0.0),
            }
        )

    return memories
