"""
Push notifications via Firebase Cloud Messaging (FCM)
Sends push notifications to iOS and Android devices.
"""

import os
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_firebase_app = None


def _init_firebase():
    """Initialize Firebase Admin SDK (singleton)"""
    global _firebase_app
    if _firebase_app is not None:
        return _firebase_app

    import firebase_admin
    from firebase_admin import credentials

    # Option 1: JSON credentials from env var (for Render deployment)
    creds_json = os.environ.get("FIREBASE_CREDENTIALS_JSON")
    if creds_json:
        cred_dict = json.loads(creds_json)
        cred = credentials.Certificate(cred_dict)
        _firebase_app = firebase_admin.initialize_app(cred)
        logger.info("Firebase initialized from FIREBASE_CREDENTIALS_JSON env var")
        return _firebase_app

    # Option 2: File path from env var
    creds_path = os.environ.get("FIREBASE_CREDENTIALS_PATH")
    if creds_path and os.path.exists(creds_path):
        cred = credentials.Certificate(creds_path)
        _firebase_app = firebase_admin.initialize_app(cred)
        logger.info(f"Firebase initialized from file: {creds_path}")
        return _firebase_app

    logger.warning("Firebase not configured: set FIREBASE_CREDENTIALS_JSON or FIREBASE_CREDENTIALS_PATH")
    return None


def _all_tokens(sb) -> list[dict]:
    """Every registered device, paging past PostgREST's 1000-row default.
    Without paging, pushes silently reached at most 1000 devices."""
    rows: list[dict] = []
    page = 1000
    while True:
        batch = sb.table("device_tokens").select(
            "fcm_token, platform, device_id, language"
        ).range(len(rows), len(rows) + page - 1).execute().data or []
        rows.extend(batch)
        if len(batch) < page:
            return rows


def send_push_to_all(title: str, body: str, data: Optional[dict] = None,
                     translations: Optional[dict] = None):
    """
    Send a push notification to ALL registered devices, each in its own language.

    `translations` maps a language code to {"title", "body"}; devices whose language
    is missing from it (or is the source language) get the original text.
    Blocking: call through send_push_async.
    """
    from supabase_client import get_supabase

    app = _init_firebase()
    if app is None:
        logger.error("Cannot send push: Firebase not initialized")
        return {"sent": 0, "failed": 0, "error": "Firebase not configured"}

    from firebase_admin import messaging

    sb = get_supabase()
    tokens = _all_tokens(sb)
    if not tokens:
        logger.info("No device tokens registered, skipping push")
        return {"sent": 0, "failed": 0}

    translations = translations or {}

    def build(row: dict) -> "messaging.Message":
        text = translations.get(row.get("language") or "", {"title": title, "body": body})
        return messaging.Message(
            notification=messaging.Notification(title=text["title"], body=text["body"]),
            data=data or {},
            token=row["fcm_token"],
            apns=messaging.APNSConfig(
                payload=messaging.APNSPayload(aps=messaging.Aps(sound="default", badge=1))
            ),
            android=messaging.AndroidConfig(
                priority="high",
                notification=messaging.AndroidNotification(
                    sound="default", channel_id="pomogaika_content",
                ),
            ),
        )

    sent = 0
    failed = 0
    stale: list[str] = []
    # FCM accepts up to 500 messages per send_each call; sending one by one was
    # a round trip per device.
    for i in range(0, len(tokens), 500):
        chunk = tokens[i:i + 500]
        try:
            batch = messaging.send_each([build(row) for row in chunk])
        except Exception as e:
            logger.error(f"Push batch {i // 500} failed entirely: {e}")
            failed += len(chunk)
            continue
        for row, resp in zip(chunk, batch.responses):
            if resp.success:
                sent += 1
            else:
                failed += 1
                if isinstance(resp.exception, messaging.UnregisteredError):
                    stale.append(row["device_id"])
                else:
                    logger.error(f"Push failed for {row['device_id']}: {resp.exception}")

    if stale:
        try:
            for i in range(0, len(stale), 100):
                sb.table("device_tokens").delete().in_("device_id", stale[i:i + 100]).execute()
            logger.info(f"Cleaned up {len(stale)} stale push tokens")
        except Exception as e:
            logger.error(f"Failed to clean stale tokens: {e}")

    by_lang = sorted({row.get("language") or "?" for row in tokens})
    logger.info(f"Push sent: {sent} ok, {failed} failed, {len(stale)} cleaned, languages {by_lang}")
    return {"sent": sent, "failed": failed, "cleaned": len(stale), "translated": sorted(translations)}


async def send_push_async(title: str, body: str, data: Optional[dict] = None,
                          source_lang: str = "ru"):
    """Translate the message into the other app languages, then send it in a
    worker thread (FCM and Supabase calls are blocking)."""
    import asyncio
    from translation import translate_push

    try:
        translations = await translate_push(title, body, source_lang)
    except Exception as e:
        # A failed translation must never block the push itself.
        logger.error(f"Push translation failed, sending the original to everyone: {e}")
        translations = {}
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, send_push_to_all, title, body, data, translations)


async def notify_new_article(article_id: str, title: str):
    """Send push notification about a new article"""
    await send_push_async(
        title="📰 Новая статья",
        body=title,
        data={"type": "article", "article_id": article_id},
    )


async def notify_new_event(event_id: str, title: str, event_date: str):
    """Send push notification about a new event"""
    await send_push_async(
        title="🎉 Новое событие",
        body=title,
        data={"type": "event", "event_id": event_id, "event_date": event_date},
    )


async def notify_event_reminder(event_id: str, title: str):
    """Send push reminder about upcoming event"""
    await send_push_async(
        title="⏰ Напоминание",
        body=f"Завтра: {title}",
        data={"type": "event_reminder", "event_id": event_id},
    )
