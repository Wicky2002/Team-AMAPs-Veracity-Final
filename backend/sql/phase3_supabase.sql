-- Phase 3 Supabase tables
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- signal_cache: avoids redundant scraping
CREATE TABLE IF NOT EXISTS signal_cache (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    domain TEXT NOT NULL,
    topic TEXT NOT NULL,
    signals JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ DEFAULT NOW() + INTERVAL '2 hours'
);

-- ab_results: written by OutreachNode, read by FeedbackIngestor
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
);

-- loop_state/checkpoints are managed by LangGraph AsyncPostgresSaver setup
