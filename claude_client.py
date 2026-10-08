"""
Shared Claude API access for the backend: one lazily created async client, and a
helper for structured-output calls (JSON schema) that checks the stop reason and
the JSON before handing back a dict.
"""

import json
import logging

import anthropic

logger = logging.getLogger(__name__)

HAIKU = "claude-haiku-5-5"

_client: anthropic.AsyncAnthropic | None = None


def get_claude() -> anthropic.AsyncAnthropic:
    # Created lazily so importing a module never needs ANTHROPIC_API_KEY.
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic()
    return _client


async def structured_json(*, system: str, user: str, schema: dict, label: str,
                          model: str = HAIKU, effort: str = "low", max_tokens: int = 4000,
                          timeout: float | None = None, max_retries: int | None = None) -> dict | None:
    """One structured-output request. Returns the parsed JSON object, or None when
    the call fails, is cut off, is declined, or doesn't return a JSON object.
    Failures are logged with `label`; callers decide what None means for them."""
    client = get_claude()
    options = {k: v for k, v in (("timeout", timeout), ("max_retries", max_retries)) if v is not None}
    if options:
        client = client.with_options(**options)
    try:
        message = await client.messages.create(
            model=model,
            # Thinking is on by default on 5.x models and counts toward this ceiling.
            max_tokens=max_tokens,
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
            system=system,
            messages=[{"role": "user", "content": user}],
        )
    except anthropic.APIError as e:
        # The SDK has already retried 429/5xx/connection errors by this point.
        logger.error(f"{label}: {type(e).__name__}: {e}")
        return None

    # Haiku 5.5 has no server-side refusal fallback, and a cut-off reply isn't valid JSON.
    if message.stop_reason != "end_turn":
        logger.error(f"{label}: stop_reason={message.stop_reason}")
        return None
    text = next((b.text for b in message.content if b.type == "text"), None)
    try:
        data = json.loads(text or "")
    except json.JSONDecodeError:
        logger.error(f"{label}: reply is not JSON: {(text or '')[:200]}")
        return None
    if not isinstance(data, dict):
        logger.error(f"{label}: reply is not a JSON object")
        return None
    return data
