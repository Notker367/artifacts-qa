# Movement tests for Artifacts MMO.
# Move is a POST action — it changes character location and triggers cooldown.
# 490 = already at destination (valid game state, not an error).
# 499 = character on cooldown from a previous action.
# Tests do not sleep — cooldown is accepted as a valid outcome where applicable.

import logging

from services.errors import ALREADY_AT_DESTINATION, ON_COOLDOWN
from services.movement import get_position, move_character, is_already_at_destination

logger = logging.getLogger(__name__)

# Coordinates used across movement tests.
# (0, 1) is a known walkable tile; adjust if the map changes.
TARGET_X, TARGET_Y = 0, 1


def test_get_current_position(client, character_name):
    """
    GET /characters/{name} must return a valid position with integer x and y.
    This is the baseline read — no action triggered, no cooldown involved.
    """
    position = get_position(client, character_name)

    assert "x" in position and "y" in position, "position must contain x and y keys"
    assert isinstance(position["x"], int), "x must be an integer"
    assert isinstance(position["y"], int), "y must be an integer"

    logger.info("current position: x=%d y=%d", position["x"], position["y"])


def test_move_returns_expected_status(client, character_name):
    """
    Moving to (TARGET_X, TARGET_Y) must return 200, 490, or 499.
    200 = moved successfully.
    490 = already there (valid — character is where we wanted it).
    499 = on cooldown from a prior action (valid — game enforces action sequencing).
    """
    response = move_character(client, character_name, TARGET_X, TARGET_Y)

    assert response.status_code in (200, ALREADY_AT_DESTINATION, ON_COOLDOWN), (
        f"unexpected status {response.status_code}: {response.text}"
    )
    logger.info("move to (%d, %d): status=%d", TARGET_X, TARGET_Y, response.status_code)


def test_move_already_at_destination_returns_490(client, character_name):
    """
    Moving to the current position must return 490.
    We first move to TARGET, then move there again — the second call must return 490
    (unless we're on cooldown, in which case 499 is also acceptable).
    """
    # First move — puts us at TARGET or confirms we're already there
    first = move_character(client, character_name, TARGET_X, TARGET_Y)
    assert first.status_code in (200, ALREADY_AT_DESTINATION, ON_COOLDOWN), (
        f"unexpected status on first move: {first.status_code}"
    )

    # Second move to same coordinates — game must reject it as already-at-destination
    second = move_character(client, character_name, TARGET_X, TARGET_Y)
    assert second.status_code in (ALREADY_AT_DESTINATION, ON_COOLDOWN), (
        f"expected 490 or 499 on repeated move, got {second.status_code}: {second.text}"
    )
    logger.info("repeated move to (%d, %d): status=%d", TARGET_X, TARGET_Y, second.status_code)


def test_move_state_visible_before_and_after(client, character_name):
    """
    After a successful move, position from GET /characters must reflect the new coordinates.
    If cooldown blocks the move, we skip the position assertion and log it.

    This verifies that the move action actually updates server-side character state,
    not just that the API returns 200.
    """
    position_before = get_position(client, character_name)
    logger.info("position before move: %s", position_before)

    response = move_character(client, character_name, TARGET_X, TARGET_Y)
    logger.info("move response: status=%d", response.status_code)

    if response.status_code == ON_COOLDOWN:
        logger.info("character on cooldown — skipping post-move position check")
        return

    assert response.status_code in (200, ALREADY_AT_DESTINATION), (
        f"unexpected move status: {response.status_code}"
    )

    position_after = get_position(client, character_name)
    logger.info("position after move: %s", position_after)

    # After a move (or confirmed already-there), position must match the target
    assert position_after["x"] == TARGET_X, (
        f"expected x={TARGET_X}, got x={position_after['x']}"
    )
    assert position_after["y"] == TARGET_Y, (
        f"expected y={TARGET_Y}, got y={position_after['y']}"
    )
