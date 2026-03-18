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


def send_push_to_all(title: str, body: str, data: Optional[dict] = None):
    """
    Send push notification to ALL registered devices.
    Called in background after article publish / event creation.
    """
    from supabase_client import get_supabase

    app = _init_firebase()
    if app is None:
        logger.error("Cannot send push: Firebase not initialized")
        return {"sent": 0, "failed": 0, "error": "Firebase not configured"}

    from firebase_admin import messaging

    # Get all device tokens
    sb = get_supabase()
    result = sb.table("device_tokens").select("fcm_token, platform, device_id").execute()
    tokens = result.data or []

    if not tokens:
        logger.info("No device tokens registered, skipping push")
        return {"sent": 0, "failed": 0}

    # Build messages for each token
    sent = 0
    failed = 0
    stale_tokens = []

    for token_row in tokens:
        fcm_token = token_row["fcm_token"]
        try:
            message = messaging.Message(
                notification=messaging.Notification(
                    title=title,
                    body=body,
                ),
                data=data or {},
                token=fcm_token,
                # iOS-specific config
                apns=messaging.APNSConfig(
                    payload=messaging.APNSPayload(
                        aps=messaging.Aps(
                            sound="default",
                            badge=1,
                        )
                    )
                ),
                # Android-specific config
                android=messaging.AndroidConfig(
                    priority="high",
                    notification=messaging.AndroidNotification(
                        sound="default",
                        channel_id="pomogaika_content",
                    )
                ),
            )
            messaging.send(message)
            sent += 1
        except messaging.UnregisteredError:
            # Token is no longer valid — mark for cleanup
            stale_tokens.append(token_row["device_id"])
            failed += 1
        except Exception as e:
            logger.error(f"Push failed for {token_row['device_id']}: {e}")
            failed += 1

    # Clean up stale tokens
    if stale_tokens:
        try:
            for device_id in stale_tokens:
                sb.table("device_tokens").delete().eq("device_id", device_id).execute()
            logger.info(f"Cleaned up {len(stale_tokens)} stale push tokens")
        except Exception as e:
            logger.error(f"Failed to clean stale tokens: {e}")

    logger.info(f"Push sent: {sent} ok, {failed} failed, {len(stale_tokens)} cleaned")
    return {"sent": sent, "failed": failed, "cleaned": len(stale_tokens)}


async def send_push_async(title: str, body: str, data: Optional[dict] = None):
    """Async wrapper — runs send_push_to_all in thread to avoid blocking"""
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, send_push_to_all, title, body, data)


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
