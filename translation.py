"""
Translation service using Claude Haiku 5.5.

Replaced MyMemory (2026-10-08). MyMemory was free machine translation with a
50K chars/day quota, and long texts had to be cut into 1500-char chunks, which
lost context between paragraphs and broke Markdown; Belarusian was the weakest.
Haiku translates each text whole, keeps the Markdown, and translating one
article into all four languages costs about half a cent.

Public API (translate_article / translate_expert / translate_event) is
unchanged, so callers in content_routes.py don't depend on the provider.
"""

import asyncio
import json
import logging
import re

from claude_client import HAIKU, structured_json

logger = logging.getLogger(__name__)

TRANSLATION_MODEL = HAIKU

# All supported app languages
ALL_LANGUAGES = ["en", "es", "ru", "uk", "be"]

# Spelled out for the model: "uk"/"be" alone invite a slide into Russian.
LANG_NAMES = {
    "en": "English",
    "es": "Spanish as spoken in Spain",
    "ru": "Russian",
    "uk": "Ukrainian (українська мова), never Russian",
    "be": "Belarusian (беларуская мова), never Russian",
}

# Photo-credit footer that content_routes appends to article bodies:
#   "\n\n---\n\n*Фото: [Name](url) / [Pexels](url)*"   (label localized per language)
# Kept here so content_routes and the translator share one copy.
ATTRIBUTION_PREFIX = {
    "ru": "Фото",
    "uk": "Фото",
    "be": "Фота",
    "en": "Photo",
    "es": "Foto",
}
# Matches the footer at the end of a body in any supported language; it keys off
# the localized label, so it matches regardless of photo source.
ATTRIBUTION_FOOTER_RE = re.compile(
    r"\s*\n\n---\n\n\*(?:Фото|Фота|Photo|Foto):.*?\*\s*$",
    re.DOTALL,
)

SYSTEM_PROMPT = """You translate content for Pomogaika, an app that helps people choose wine in Spanish supermarkets (Consum, Mercadona, Masymas, DIA, Condis, Froiz).

Translate the value of every field in the JSON you are given, and return the same fields.

- Keep the meaning and the friendly, unpretentious voice. It should read as if written in the target language, not translated.
- Preserve the Markdown exactly: **bold**, *italic*, headings, lists, blank lines between paragraphs, --- separators and links. Translate link text, never change a URL.
- Keep wine names, grape varieties, D.O. regions, store names and brands as written.
- Keep people's names as written."""

async def _translate_fields(fields: dict[str, str], source_lang: str, target_lang: str) -> dict[str, str] | None:
    """
    Translate a set of named text fields in one request.
    Returns {field: translation} with every field present, or None on failure.
    """
    fields = {k: v for k, v in fields.items() if v and v.strip()}
    if not fields:
        return None
    if source_lang == target_lang:
        return fields

    schema = {
        "type": "object",
        "properties": {name: {"type": "string"} for name in fields},
        "required": list(fields),
        "additionalProperties": False,
    }
    pair = f"{source_lang}->{target_lang}"

    try:
        return await _request(fields, schema, source_lang, target_lang, pair)
    except Exception:
        # One language failing must not discard the others, already paid for.
        logger.exception(f"Translation {pair}: unexpected error")
        return None


async def _request(fields: dict[str, str], schema: dict, source_lang: str, target_lang: str, pair: str) -> dict[str, str] | None:
    data = await structured_json(
        system=SYSTEM_PROMPT,
        user=(f"Translate from {LANG_NAMES.get(source_lang, source_lang)} into "
              f"{LANG_NAMES.get(target_lang, target_lang)}.\n\n" + json.dumps(fields, ensure_ascii=False)),
        schema=schema,
        label=f"Translation {pair}",
        model=TRANSLATION_MODEL,
        effort="low",          # translation doesn't need deep reasoning
        max_tokens=16000,      # a whole article body plus thinking
    )
    if data is None:
        return None
    result = {name: (data.get(name) or "").strip() for name in fields}
    if not all(result.values()):
        logger.warning(f"Translation {pair}: empty field(s) {[k for k, v in result.items() if not v]}")
        return None
    return result


async def _translate_to_all(fields: dict[str, str], source_lang: str) -> dict[str, dict[str, str]]:
    """Translate fields into every other app language in parallel."""
    targets = [lang for lang in ALL_LANGUAGES if lang != source_lang]
    results = await asyncio.gather(*(_translate_fields(fields, source_lang, lang) for lang in targets))
    return {lang: r for lang, r in zip(targets, results) if r}


async def translate_article(title: str, body: str, source_lang: str) -> dict:
    """
    Translate article title and body to all app languages (except source).
    Returns dict: {"en": {"title": "...", "body": "..."}, "es": {...}, ...}
    """
    # The photo credit isn't prose: keep it away from the model and re-attach it
    # with each language's exact label, so ATTRIBUTION_FOOTER_RE still finds it.
    match = ATTRIBUTION_FOOTER_RE.search(body or "")
    text = body[:match.start()] if match else (body or "")
    if not text.strip():
        logger.warning("Article has no body text to translate")
        return {}

    translations = await _translate_to_all({"title": title, "body": text}, source_lang)
    for lang, entry in translations.items():
        if match:
            footer = re.sub(r"\*(?:Фото|Фота|Photo|Foto):", f"*{ATTRIBUTION_PREFIX[lang]}:",
                            match.group(0).strip(), count=1)
            entry["body"] = entry["body"].rstrip() + "\n\n" + footer
        logger.info(f"Translated article to {lang}: OK (body_len={len(entry['body'])})")
    return translations


async def translate_expert(bio: str | None, source_lang: str) -> dict:
    """
    Translate an expert's bio to all app languages.
    Returns dict: {"en": {"bio": "..."}, ...}

    NOTE: the expert's NAME is deliberately NOT machine-translated - these are real
    people. Names are curated by hand in the admin (transliterated for en/es, left in
    Cyrillic for uk/be). This helper only fills in the bio; any existing hand-written
    name stays untouched by the caller.
    """
    if not bio:
        return {}
    translations = await _translate_to_all({"bio": bio}, source_lang)
    for lang in translations:
        logger.info(f"Translated expert bio to {lang}: OK")
    return translations


async def translate_event(title: str, description: str | None, source_lang: str) -> dict:
    """
    Translate event title and description to all app languages.
    Returns dict: {"en": {"title": "...", "description": "..."}, ...}
    """
    fields = {"title": title}
    if description:
        fields["description"] = description
    translations = await _translate_to_all(fields, source_lang)
    for lang in translations:
        logger.info(f"Translated event to {lang}: OK")
    return translations


async def translate_push(title: str, body: str, source_lang: str = "ru") -> dict:
    """Push title/body in every other app language: {"en": {"title", "body"}, ...}.
    A language whose translation fails is simply absent; those devices get the original."""
    translations = await _translate_to_all({"title": title, "body": body}, source_lang)
    logger.info(f"Push translated to {sorted(translations)}")
    return translations
