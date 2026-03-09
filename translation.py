"""
Translation service using MyMemory API
Free tier: 5000 chars/day (anonymous), 50000 chars/day (with email)
Same approach as NatureSpot project
"""

import httpx
import asyncio
import logging

logger = logging.getLogger(__name__)

MYMEMORY_URL = "https://api.mymemory.translated.net/get"
MYMEMORY_EMAIL = "pomogaika.app@gmail.com"  # for 50K chars/day limit

# Language codes for MyMemory API
LANG_CODES = {
    "en": "en-GB",
    "es": "es-ES",
    "ru": "ru-RU",
    "uk": "uk-UA",
    "be": "be-BY",
}

# All supported app languages
ALL_LANGUAGES = ["en", "es", "ru", "uk", "be"]

# Delay between API calls to respect rate limits (ms)
API_DELAY_SEC = 0.3
MIN_TEXT_LENGTH = 3
REQUEST_TIMEOUT = 10.0
# Max chars per single API request (MyMemory limit with email is ~10K,
# but we keep it lower to stay safe with URL encoding on fallback)
MAX_CHUNK_CHARS = 1500


async def check_quota() -> bool:
    """Quick check if MyMemory quota is still available.
    Returns True if quota OK, False if exhausted (429).
    """
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.post(
                MYMEMORY_URL,
                data={
                    "q": "тест",
                    "langpair": "ru-RU|en-GB",
                    "de": MYMEMORY_EMAIL,
                }
            )
            data = resp.json()
            if data.get("responseStatus") == 429:
                logger.error("MyMemory daily quota exhausted!")
                return False
            return True
    except Exception as e:
        logger.error(f"Quota check failed: {e}")
        return True  # assume OK on error, let real translation handle it


async def translate_text(text: str, source_lang: str, target_lang: str) -> str | None:
    """
    Translate a single text chunk using MyMemory API (POST to avoid URL length limits).
    Returns translated text or None on failure.
    """
    if not text or len(text.strip()) < MIN_TEXT_LENGTH:
        return None

    if source_lang == target_lang:
        return text

    source_code = LANG_CODES.get(source_lang, source_lang)
    target_code = LANG_CODES.get(target_lang, target_lang)
    langpair = f"{source_code}|{target_code}"

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            # Use POST to avoid URL length limits with long Cyrillic texts
            response = await client.post(
                MYMEMORY_URL,
                data={
                    "q": text,
                    "langpair": langpair,
                    "de": MYMEMORY_EMAIL,
                }
            )
            data = response.json()

            status = data.get("responseStatus")
            if status == 429:
                logger.error(
                    f"MyMemory QUOTA EXHAUSTED for {langpair}: "
                    f"daily limit reached. Translation will resume tomorrow."
                )
                return None

            if status != 200:
                logger.warning(
                    f"MyMemory error for {langpair}: status={status}, "
                    f"text_len={len(text)}, response={str(data)[:200]}"
                )
                return None

            translated = data.get("responseData", {}).get("translatedText", "")

            # Skip UPPERCASE responses (MyMemory quirk when it can't translate)
            if translated and translated == translated.upper() and not text == text.upper():
                logger.warning(f"Skipping UPPERCASE response for {langpair}: {translated[:50]}")
                return None

            return translated if translated else None

    except Exception as e:
        logger.error(f"Translation error ({langpair}): text_len={len(text)}, error={e}")
        return None


async def translate_long_text(text: str, source_lang: str, target_lang: str) -> str | None:
    """
    Translate long text by splitting into paragraphs/chunks if needed.
    Handles article bodies that may exceed MyMemory per-request limits.
    Returns translated text or None on complete failure.
    """
    if not text or len(text.strip()) < MIN_TEXT_LENGTH:
        return None

    # Short text — translate directly
    if len(text) <= MAX_CHUNK_CHARS:
        return await translate_text(text, source_lang, target_lang)

    # Split by newlines (paragraphs)
    paragraphs = text.split('\n')
    translated_parts = []
    any_success = False

    for para in paragraphs:
        stripped = para.strip()

        # Preserve empty lines
        if not stripped:
            translated_parts.append('')
            continue

        # If paragraph is short enough, translate directly
        if len(stripped) <= MAX_CHUNK_CHARS:
            translated = await translate_text(stripped, source_lang, target_lang)
            await asyncio.sleep(API_DELAY_SEC)

            if translated:
                translated_parts.append(translated)
                any_success = True
            else:
                translated_parts.append(stripped)  # Keep original on failure
        else:
            # Very long paragraph — split by sentences (. ! ?)
            sentences = _split_into_chunks(stripped, MAX_CHUNK_CHARS)
            translated_sentences = []

            for sentence in sentences:
                if not sentence.strip():
                    continue
                translated = await translate_text(sentence.strip(), source_lang, target_lang)
                await asyncio.sleep(API_DELAY_SEC)

                if translated:
                    translated_sentences.append(translated)
                    any_success = True
                else:
                    translated_sentences.append(sentence.strip())

            translated_parts.append(' '.join(translated_sentences))

    if not any_success:
        return None

    return '\n'.join(translated_parts)


def _split_into_chunks(text: str, max_chars: int) -> list[str]:
    """Split text into chunks at sentence boundaries, respecting max_chars limit."""
    import re

    # Split by sentence-ending punctuation (keep the delimiter)
    parts = re.split(r'(?<=[.!?])\s+', text)
    chunks = []
    current_chunk = ""

    for part in parts:
        if not part:
            continue
        if len(current_chunk) + len(part) + 1 <= max_chars:
            current_chunk = (current_chunk + " " + part).strip()
        else:
            if current_chunk:
                chunks.append(current_chunk)
            # If single sentence exceeds limit, just add it anyway
            current_chunk = part

    if current_chunk:
        chunks.append(current_chunk)

    return chunks if chunks else [text]


async def translate_article(title: str, body: str, source_lang: str) -> dict:
    """
    Translate article title and body to all app languages (except source).
    Returns dict: {"en": {"title": "...", "body": "..."}, "es": {...}, ...}
    Uses chunked translation for long article bodies.
    """
    translations = {}
    target_languages = [lang for lang in ALL_LANGUAGES if lang != source_lang]

    for lang in target_languages:
        translated_title = await translate_text(title, source_lang, lang)
        await asyncio.sleep(API_DELAY_SEC)

        # Use chunked translation for body (may be 500-800 words)
        translated_body = await translate_long_text(body, source_lang, lang)
        await asyncio.sleep(API_DELAY_SEC)

        if translated_title and translated_body:
            translations[lang] = {
                "title": translated_title,
                "body": translated_body,
            }
            logger.info(f"Translated article to {lang}: OK (body_len={len(translated_body)})")
        else:
            logger.warning(
                f"Translation to {lang} incomplete: title={bool(translated_title)}, "
                f"body={bool(translated_body)}, body_input_len={len(body)}"
            )

    return translations


async def translate_event(title: str, description: str | None, source_lang: str) -> dict:
    """
    Translate event title and description to all app languages.
    Returns dict: {"en": {"title": "...", "description": "..."}, ...}
    Uses chunked translation for long descriptions.
    """
    translations = {}
    target_languages = [lang for lang in ALL_LANGUAGES if lang != source_lang]

    for lang in target_languages:
        translated_title = await translate_text(title, source_lang, lang)
        await asyncio.sleep(API_DELAY_SEC)

        translated_desc = None
        if description:
            translated_desc = await translate_long_text(description, source_lang, lang)
            await asyncio.sleep(API_DELAY_SEC)

        if translated_title:
            entry = {"title": translated_title}
            if translated_desc:
                entry["description"] = translated_desc
            translations[lang] = entry
            logger.info(f"Translated event to {lang}: OK")

    return translations
