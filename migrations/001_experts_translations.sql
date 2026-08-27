-- Migration: localized experts (2026-08-27)
--
-- Adds a `translations` JSONB column to public.experts, mirroring articles/events.
-- Shape: {"en": {"name": "Nikolay", "bio": "..."}, "es": {...}, "uk": {"bio": "..."}}
--
-- Convention (see translation.translate_expert / content_routes._localize_expert):
--   * source language is always ru — there is no per-row `language` column here
--   * `name` is curated BY HAND: transliterated for en/es, and deliberately omitted for
--     uk/be so it falls back to the original Cyrillic. Machine translation mangles
--     proper nouns, and these are real people.
--   * `bio` is machine-translated via POST /admin/experts/{id}/translate
--   * name and bio fall back independently, so a partially filled entry is fine
--
-- GRANTs: not needed. This ALTERs an existing table, which keeps its current grants.
-- (The Oct 30 2026 Supabase change only removes default grants for NEWLY created
-- tables — see critical-rules.md.)

ALTER TABLE public.experts
    ADD COLUMN IF NOT EXISTS translations JSONB DEFAULT '{}'::jsonb;
