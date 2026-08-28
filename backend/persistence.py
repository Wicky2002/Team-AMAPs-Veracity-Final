from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any

try:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg.types.json import Json
except Exception:  # pragma: no cover - optional dependency guard
    psycopg = None
    dict_row = None
    Json = None

from state import CycleResult, OutreachVariant, SignalReference

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
    "ALTER TABLE ab_results ADD COLUMN IF NOT EXISTS image_url TEXT",
    "ALTER TABLE ab_results ADD COLUMN IF NOT EXISTS discord_message_id TEXT",
    """
    CREATE TABLE IF NOT EXISTS campaign_history (
        id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
        thread_id TEXT NOT NULL,
        cycle_n INTEGER NOT NULL,
        top_signal TEXT,
        winning_variant TEXT,
        open_rate FLOAT,
        reply_rate FLOAT,
        angle TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW()
    )
    """,
    "ALTER TABLE campaign_history ADD COLUMN IF NOT EXISTS channel TEXT",
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
        return await psycopg.AsyncConnection.connect(conn_str, autocommit=True, connect_timeout=5)
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
    discord_message_ids: list[str] | None = None,
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

                variant = variants[idx] if 0 <= idx < len(variants) else None
                hypothesis = variant.hypothesis if variant else None
                image_url = variant.image_url if variant else None
                discord_message_id = (
                    discord_message_ids[idx]
                    if discord_message_ids and 0 <= idx < len(discord_message_ids)
                    else None
                )

                await cur.execute(
                    """
                    INSERT INTO ab_results (
                        thread_id, cycle_n, variant_id, hypothesis,
                        open_rate, reply_rate, ctr, image_url, discord_message_id
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        thread_id,
                        cycle_n,
                        _variant_label(idx),
                        hypothesis,
                        float(metric.get("open_rate", 0.0)),
                        float(metric.get("reply_rate", 0.0)),
                        float(metric.get("click_rate", metric.get("ctr", 0.0))),
                        image_url,
                        discord_message_id,
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


async def save_campaign_history(*, thread_id: str, cycle_result: CycleResult) -> None:
    """Persist one closed cycle's result so cross-cycle learning is durable and
    queryable outside of the LangGraph checkpoint (needed for a real-time view)."""
    if not await ensure_phase3_tables():
        return

    conn = await _connect()
    if conn is None:
        return

    try:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO campaign_history (
                    thread_id, cycle_n, top_signal, winning_variant, open_rate, reply_rate, angle, channel
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    thread_id,
                    cycle_result.cycle_n,
                    cycle_result.top_signal,
                    cycle_result.winning_variant,
                    cycle_result.open_rate,
                    cycle_result.reply_rate,
                    cycle_result.angle,
                    cycle_result.channel,
                ),
            )
    except Exception:
        return
    finally:
        await conn.close()


async def load_campaign_history(thread_id: str) -> list[CycleResult] | None:
    if not await ensure_phase3_tables():
        return None

    conn = await _connect()
    if conn is None:
        return None

    try:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT cycle_n, top_signal, winning_variant, open_rate, reply_rate, angle, channel, created_at
                FROM campaign_history
                WHERE thread_id = %s
                ORDER BY created_at ASC
                """,
                (thread_id,),
            )
            rows = await cur.fetchall()

        if not rows:
            return None

        history: list[CycleResult] = []
        for row in rows:
            try:
                history.append(
                    CycleResult(
                        cycle_n=int(row.get("cycle_n", 0)),
                        top_signal=str(row.get("top_signal") or ""),
                        winning_variant=str(row.get("winning_variant") or ""),
                        open_rate=float(row.get("open_rate") or 0.0),
                        reply_rate=float(row.get("reply_rate") or 0.0),
                        angle=row.get("angle") or "competitor_gap",
                        channel=row.get("channel") or None,
                        timestamp=(
                            row.get("created_at").isoformat()
                            if row.get("created_at")
                            else datetime.now(timezone.utc).isoformat()
                        ),
                    )
                )
            except Exception:
                continue
        return history or None
    except Exception:
        return None
    finally:
        await conn.close()
