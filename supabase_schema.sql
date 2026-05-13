-- Pomogaika v2: Database Schema
-- Run this in Supabase SQL Editor (SQL Editor → New query → Run)

-- 1. Admin users table (links to Supabase Auth)
CREATE TABLE admin_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    auth_user_id UUID UNIQUE NOT NULL,  -- links to auth.users.id
    email TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'editor')),
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Experts (wine experts who write articles)
CREATE TABLE experts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    bio TEXT,
    avatar_url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Articles (expert blog posts)
CREATE TABLE articles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    expert_id UUID NOT NULL REFERENCES experts(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    image_url TEXT,
    language TEXT NOT NULL DEFAULT 'ru',  -- source language
    translations JSONB DEFAULT '{}'::jsonb,  -- {"en": {"title": "...", "body": "..."}, "es": {...}}
    is_published BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4. Events (wine tasting events, degustations)
CREATE TABLE events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    description TEXT,
    event_date TIMESTAMPTZ NOT NULL,
    telegram_url TEXT,  -- Telegram channel/group link
    image_url TEXT,
    language TEXT NOT NULL DEFAULT 'ru',  -- source language
    translations JSONB DEFAULT '{}'::jsonb,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 5. Event clicks (user registrations / click-throughs)
CREATE TABLE event_clicks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    user_name TEXT NOT NULL,
    user_surname TEXT NOT NULL,
    device_id TEXT,  -- unique device identifier for tracking
    platform TEXT,   -- 'ios' or 'android'
    clicked_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX idx_articles_expert ON articles(expert_id);
CREATE INDEX idx_articles_published ON articles(is_published, created_at DESC);
CREATE INDEX idx_events_active ON events(is_active, event_date);
CREATE INDEX idx_event_clicks_event ON event_clicks(event_id);
CREATE INDEX idx_event_clicks_device ON event_clicks(device_id);

-- Auto-update updated_at on articles
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER articles_updated_at
    BEFORE UPDATE ON articles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER events_updated_at
    BEFORE UPDATE ON events
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- =====================================================================
-- Data API grants for service_role
-- =====================================================================
-- Required as of Supabase platform change:
--   * New projects (from May 30 2026): no default grants on new tables
--   * Existing projects (from Oct 30 2026): same — new tables only
-- Existing tables on prod Supabase keep their original grants; the
-- statements below are idempotent (safe to re-run) and serve as the
-- canonical template for any future table added to public.
--
-- We grant only service_role: backend FastAPI talks to Supabase via
-- the REST API with the service-role key. iOS/Android clients NEVER
-- access Supabase directly, so anon/authenticated grants are
-- intentionally omitted (attack-surface reduction).
--
-- Any new CREATE TABLE public.<name> added below or in follow-up
-- migrations MUST include a matching GRANT statement here.
-- =====================================================================

GRANT SELECT, INSERT, UPDATE, DELETE ON public.admin_users   TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.experts       TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.articles      TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.events        TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.event_clicks  TO service_role;

-- NOTE: 4 tables added to prod Supabase later via direct SQL Editor and
-- NOT present as CREATE TABLE blocks above (content_reactions,
-- article_views, event_views, device_tokens). They keep their default
-- grants on the live project until Oct 30 2026. If this schema file
-- is ever used to re-provision from scratch, those tables and their
-- grants will need to be added here first.
