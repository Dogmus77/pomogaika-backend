"""
Supabase client for Pomogaika
Connects to Supabase PostgreSQL for articles, events, experts, auth
Auto-reconnects if connection is lost.
"""

import os
import logging
from supabase import create_client, Client, ClientOptions

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


# Supabase Auth calls (sign-in, refresh, token checks) must NOT run on the shared
# get_supabase() client. supabase-py keeps the session it signs in with and then
# switches that client's DB requests from the service key to the user's 1-hour JWT,
# so the whole backend ran as the last admin who logged in. Once that token expired,
# any admin with a still-valid token of their own got a 500 from get_current_user.
_AUTH_OPTIONS = ClientOptions(auto_refresh_token=False, persist_session=False)
_auth_client: Client | None = None


def get_auth_client() -> Client:
    """Shared client for stateless auth calls only (get_user with an explicit JWT)."""
    global _auth_client
    if _auth_client is None:
        _auth_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY, options=_AUTH_OPTIONS)
    return _auth_client


def new_auth_client() -> Client:
    """Throwaway client for calls that start a session (sign-in, refresh), so no
    session state is ever shared between requests or users."""
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY, options=_AUTH_OPTIONS)


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
