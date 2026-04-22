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

_tables_ready = False
_tables_lock = asyncio.Lock()


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
