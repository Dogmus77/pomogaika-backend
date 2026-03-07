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


async def translate_text(text: str, source_lang: str, target_lang: str) -> str | None:
    """
    Translate text using MyMemory API.
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
            response = await client.get(
                MYMEMORY_URL,
                params={
                    "q": text,
                    "langpair": langpair,
                    "de": MYMEMORY_EMAIL,
                }
            )
            data = response.json()

            if data.get("responseStatus") != 200:
                logger.warning(
                    f"MyMemory error for {langpair}: {data.get('responseStatus')}"
                )
                return None

            translated = data.get("responseData", {}).get("translatedText", "")

            # Skip UPPERCASE responses (MyMemory quirk when it can't translate)
            if translated and translated == translated.upper() and not text == text.upper():
                logger.warning(f"Skipping UPPERCASE response for {langpair}: {translated[:50]}")
                return None

            return translated if translated else None

    except Exception as e:
        logger.error(f"Translation error ({langpair}): {e}")
        return None


async def translate_article(title: str, body: str, source_lang: str) -> dict:
    """
    Translate article title and body to all app languages (except source).
    Returns dict: {"en": {"title": "...", "body": "..."}, "es": {...}, ...}
    """
    translations = {}
    target_languages = [lang for lang in ALL_LANGUAGES if lang != source_lang]

    for lang in target_languages:
        translated_title = await translate_text(title, source_lang, lang)
        await asyncio.sleep(API_DELAY_SEC)

        translated_body = await translate_text(body, source_lang, lang)
        await asyncio.sleep(API_DELAY_SEC)

        if translated_title and translated_body:
            translations[lang] = {
                "title": translated_title,
                "body": translated_body,
            }
            logger.info(f"Translated article to {lang}: OK")
        else:
            logger.warning(f"Translation to {lang} incomplete: title={bool(translated_title)}, body={bool(translated_body)}")

    return translations


async def translate_event(title: str, description: str | None, source_lang: str) -> dict:
    """
    Translate event title and description to all app languages.
    Returns dict: {"en": {"title": "...", "description": "..."}, ...}
    """
    translations = {}
    target_languages = [lang for lang in ALL_LANGUAGES if lang != source_lang]

    for lang in target_languages:
        translated_title = await translate_text(title, source_lang, lang)
        await asyncio.sleep(API_DELAY_SEC)

        translated_desc = None
        if description:
            translated_desc = await translate_text(description, source_lang, lang)
            await asyncio.sleep(API_DELAY_SEC)

        if translated_title:
            entry = {"title": translated_title}
            if translated_desc:
                entry["description"] = translated_desc
            translations[lang] = entry
            logger.info(f"Translated event to {lang}: OK")

    return translations
