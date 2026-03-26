# Multi-character helpers for Artifacts MMO.
# GET /my/characters returns all account characters in one call — use this
# instead of N separate GET /characters/{name} calls in dispatch loops.
#
# Core dispatch model (from roles_and_optimization.md):
#   - one sequential loop, no threads
#   - cooldowns run in parallel while the loop sleeps
#   - roles are pre-assigned per character, not chosen dynamically
#   - sleep exactly until the next character becomes ready
#
# Role assignment lives in a simple dict — changing a role = changing one line:
#
#   ROLES = {
#       "Furiba":     "combat",
#       "Fussat":     "combat",
#       "Velikossat": "woodcutting",
#       "Ognerot":    "mining",
#       "Mikrochelo": "alchemy",
#   }

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def get_all_characters(client) -> list:
    """
    Fetch all account characters in a single API call.
    Returns a list of character data dicts — same structure as GET /characters/{name}.
    Use this as the entry point for every dispatch loop iteration.
    """
    response = client.get("/my/characters")
    response.raise_for_status()
    return response.json().get("data", [])


def seconds_until_ready(char_data: dict) -> float:
    """
    Return how many seconds until this character's cooldown expires.
    Returns 0.0 if the character is ready to act right now.
    Works on already-fetched character data — makes no API call.
    """
    expiration = char_data.get("cooldown_expiration")
    if not expiration:
        return 0.0

    expires_at = datetime.fromisoformat(expiration.replace("Z", "+00:00"))
    remaining = (expires_at - datetime.now(timezone.utc)).total_seconds()
    return max(0.0, remaining)


def find_ready_characters(characters: list) -> list:
    """
    Return all characters whose cooldown has expired and are ready to act.
    Call this each loop iteration to get the action candidates for this cycle.
    """
    return [ch for ch in characters if seconds_until_ready(ch) == 0.0]


def find_next_ready(characters: list) -> dict | None:
    """
    Return the character with the shortest remaining cooldown.
    Used to determine how long to sleep before the next action is possible.
    Returns None if the list is empty.
    """
    if not characters:
        return None
    return min(characters, key=seconds_until_ready)


def sleep_until_next_ready(characters: list) -> float:
    """
    Return the number of seconds to sleep until the next character becomes ready.
    Add a small buffer (0.3s) to account for clock drift between client and API.
    Returns 0.0 if any character is already ready.
    """
    if not characters:
        return 0.0
    next_char = find_next_ready(characters)
    wait = seconds_until_ready(next_char)
    if wait <= 0:
        return 0.0
    logger.debug(
        "next ready: %s in %.1fs", next_char.get("name"), wait
    )
    return wait + 0.3  # buffer for clock drift
