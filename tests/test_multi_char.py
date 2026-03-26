# Multi-character tests for Artifacts MMO.
# GET /my/characters returns all account characters in one call.
# These tests verify that the data is complete enough to drive dispatch decisions:
# who is ready, who is next, what role to run.

import logging
import os
from datetime import datetime, timezone, timedelta

from services.multi_char import (
    get_all_characters,
    seconds_until_ready,
    find_ready_characters,
    find_next_ready,
    sleep_until_next_ready,
)

logger = logging.getLogger(__name__)

# All character names from env — dispatch loop must account for all of them
ALL_CHARACTER_NAMES = [
    os.getenv("ARTIFACTS_CHARACTER_1", ""),
    os.getenv("ARTIFACTS_CHARACTER_2", ""),
    os.getenv("ARTIFACTS_CHARACTER_3", ""),
    os.getenv("ARTIFACTS_CHARACTER_4", ""),
    os.getenv("ARTIFACTS_CHARACTER_5", ""),
]


def test_get_all_characters_returns_all_five(client):
    """
    GET /my/characters must return all 5 account characters.
    Each name from env must appear exactly once in the response.
    """
    characters = get_all_characters(client)
    assert len(characters) == 5, f"expected 5 characters, got {len(characters)}"

    names_in_response = {ch["name"] for ch in characters}
    for name in ALL_CHARACTER_NAMES:
        assert name in names_in_response, (
            f"character {name!r} from env not found in /my/characters response"
        )

    logger.info("all characters: %s", sorted(names_in_response))


def test_character_data_has_fields_for_dispatch(client):
    """
    Each character must carry the fields needed for dispatch decisions:
    identity, health, position, cooldown, and task state.
    """
    characters = get_all_characters(client)

    dispatch_fields = (
        "name", "hp", "max_hp", "x", "y",
        "cooldown_expiration",
        "task", "task_type", "task_progress", "task_total",
    )

    for ch in characters:
        for field in dispatch_fields:
            assert field in ch, (
                f"character {ch.get('name')!r} missing dispatch field: {field!r}"
            )

        ready = seconds_until_ready(ch)
        logger.info(
            "%s | hp=%d/%d pos=(%d,%d) ready_in=%.1fs task=%r %d/%d",
            ch["name"], ch["hp"], ch["max_hp"],
            ch["x"], ch["y"], ready,
            ch["task"], ch["task_progress"], ch["task_total"],
        )


def test_seconds_until_ready_logic():
    """
    seconds_until_ready must correctly compute remaining cooldown from character data.
    Works on plain dicts — no API needed.
    """
    now = datetime.now(timezone.utc)

    # Already expired — ready now
    past = {"cooldown_expiration": (now - timedelta(seconds=10)).isoformat()}
    assert seconds_until_ready(past) == 0.0, "expired cooldown must return 0.0"

    # No cooldown field at all — ready now
    assert seconds_until_ready({}) == 0.0, "missing field must return 0.0"
    assert seconds_until_ready({"cooldown_expiration": None}) == 0.0

    # Future cooldown
    future = {"cooldown_expiration": (now + timedelta(seconds=30)).isoformat()}
    remaining = seconds_until_ready(future)
    assert 28.0 < remaining <= 30.0, f"expected ~30s remaining, got {remaining:.1f}s"

    logger.info("seconds_until_ready: all logic checks passed")


def test_find_next_ready_returns_soonest(client):
    """
    find_next_ready must return the character with the smallest remaining cooldown.
    sleep_until_next_ready must return a non-negative float.
    """
    characters = get_all_characters(client)

    next_char = find_next_ready(characters)
    assert next_char is not None, "find_next_ready must return a character"

    soonest = seconds_until_ready(next_char)
    for ch in characters:
        assert seconds_until_ready(ch) >= soonest, (
            f"{ch['name']} is ready sooner than find_next_ready result"
        )

    sleep_time = sleep_until_next_ready(characters)
    assert sleep_time >= 0.0, "sleep time must be non-negative"

    ready = find_ready_characters(characters)
    logger.info(
        "ready now: %s | next: %s in %.1fs | sleep: %.1fs",
        [ch["name"] for ch in ready],
        next_char["name"],
        soonest,
        sleep_time,
    )
