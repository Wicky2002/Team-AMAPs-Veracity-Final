-- Phase 3 Supabase tables
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

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

-- response_memory: retrieval memory for cross-thread prompt augmentation
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
);

CREATE INDEX IF NOT EXISTS idx_response_memory_created_at
    ON response_memory (created_at DESC);

-- loop_state/checkpoints are managed by LangGraph AsyncPostgresSaver setup
