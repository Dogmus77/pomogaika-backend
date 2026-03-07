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
