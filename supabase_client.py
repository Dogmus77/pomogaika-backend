"""
Supabase client for Pomogaika
Connects to Supabase PostgreSQL for articles, events, experts, auth
Auto-reconnects if connection is lost.
"""

import os
import logging
from supabase import create_client, Client

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

_client: Client | None = None


def _create_client() -> Client:
    """Create a fresh Supabase client"""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in environment"
        )
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


def get_supabase() -> Client:
    """Get or create Supabase client (singleton)"""
    global _client
    if _client is None:
        _client = _create_client()
    return _client


def reset_supabase():
    """Reset the Supabase client (forces reconnection on next call)"""
    global _client
    _client = None
    logger.info("Supabase client reset, will reconnect on next request")


def supabase_query(func):
    """
    Decorator that auto-retries Supabase queries once on connection failure.
    If first attempt fails, resets the client and retries with a fresh connection.
    """
    import functools

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            error_name = type(e).__name__
            logger.warning(
                f"Supabase query failed ({error_name}: {e}), "
                f"resetting client and retrying..."
            )
            reset_supabase()
            # Retry once with fresh client
            return await func(*args, **kwargs)

    return wrapper
