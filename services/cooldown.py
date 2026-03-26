# Cooldown is a core game mechanic in Artifacts MMO, not just rate limiting.
# Every character action returns cooldown data in the response body.
# These helpers make cooldown state readable and reusable across services.

import logging
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# HTTP status code the API returns when a character is still in cooldown
COOLDOWN_STATUS_CODE = 499


def is_on_cooldown(response) -> bool:
    """
    Return True if the API rejected the action because the character is on cooldown.
    Use this to distinguish cooldown from other failures without hardcoding 499 everywhere.
    """
    return response.status_code == COOLDOWN_STATUS_CODE


def parse_cooldown(response) -> dict | None:
    """
    Extract cooldown data from a successful action response.
    Artifacts includes cooldown info in the 'data.cooldown' field after every action.
    Returns None if the response has no cooldown data (e.g. GET requests, error responses).
    """
    try:
        return response.json().get("data", {}).get("cooldown")
    except Exception:
        return None


def remaining_seconds(response) -> float | None:
    """
    Return remaining cooldown seconds from an action response, or None if not present.
    Useful for logging how long until the character can act again.
    """
    cooldown = parse_cooldown(response)
    if cooldown is None:
        return None
    return cooldown.get("remaining_seconds")


def wait_for_cooldown(client, character_name: str, max_wait: float = 120.0) -> None:
    """
    Block until the character's cooldown expires, then return.
    Reads cooldown_expiration from GET /characters/{name} — works at any point,
    not just after an action response. Use before any action that must not be blocked.
    Raises TimeoutError if the remaining cooldown exceeds max_wait seconds.
    """
    response = client.get(f"/characters/{character_name}")
    response.raise_for_status()
    expiration = response.json()["data"].get("cooldown_expiration")

    if not expiration:
        return  # character is not on cooldown

    expires_at = datetime.fromisoformat(expiration.replace("Z", "+00:00"))
    wait = (expires_at - datetime.now(timezone.utc)).total_seconds()

    if wait <= 0:
        return  # already expired

    if wait > max_wait:
        raise TimeoutError(
            f"cooldown too long: {wait:.1f}s exceeds max_wait={max_wait}s"
        )

    logger.info("cooldown: waiting %.1fs for %s", wait, character_name)
    time.sleep(wait + 0.3)  # small buffer for clock drift
