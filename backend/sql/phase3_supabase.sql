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

-- ab_results: written by OutreachNode + /loop/refresh_engagement, read by FeedbackIngestor.
-- image_url / discord_message_id trace each metric row back to the exact
-- generated creative and the real Discord post it came from.
CREATE TABLE IF NOT EXISTS ab_results (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    thread_id TEXT NOT NULL,
    cycle_n INTEGER NOT NULL,
    variant_id TEXT NOT NULL,
    hypothesis TEXT,
    open_rate FLOAT,
    reply_rate FLOAT,
    ctr FLOAT,
    image_url TEXT,
    discord_message_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE ab_results ADD COLUMN IF NOT EXISTS image_url TEXT;
ALTER TABLE ab_results ADD COLUMN IF NOT EXISTS discord_message_id TEXT;

-- campaign_history: durable, queryable copy of each closed cycle's winner --
-- the LangGraph checkpoint keeps this too, but only this table survives
-- outside the chat thread for a real-time / cross-cycle view.
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
);
ALTER TABLE campaign_history ADD COLUMN IF NOT EXISTS channel TEXT;

-- loop_state/checkpoints are managed by LangGraph AsyncPostgresSaver setup
