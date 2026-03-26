# Movement tests for Artifacts MMO.
# Move is a POST action — it changes character location and triggers cooldown.
# All stateful tests call wait_for_cooldown before acting so results are deterministic.
# 490 and 499 are tested as distinct scenarios, not lumped together.

import logging

from services.errors import ALREADY_AT_DESTINATION, ON_COOLDOWN
from services.cooldown import wait_for_cooldown
from services.movement import get_position, move_character, is_already_at_destination

logger = logging.getLogger(__name__)

# Two distinct walkable tiles used to produce controlled state transitions.
# A → B tests successful move; B → B tests already-at-destination (490).
TILE_A = (0, 0)
TILE_B = (0, 1)


def test_get_current_position(client, character_name):
    """
    GET /characters/{name} must return a valid position with integer x and y.
    No action triggered — baseline read, no cooldown involved.
    """
    position = get_position(client, character_name)

    assert "x" in position and "y" in position, "position must contain x and y keys"
    assert isinstance(position["x"], int), "x must be an integer"
    assert isinstance(position["y"], int), "y must be an integer"

    logger.info("current position: x=%d y=%d", position["x"], position["y"])


def test_move_changes_position(client, character_name):
    """
    After a successful move, GET /characters must reflect the new coordinates.
    Verifies that the action actually updates server-side character state.
    """
    wait_for_cooldown(client, character_name)
    move_character(client, character_name, *TILE_A)

    wait_for_cooldown(client, character_name)
    response = move_character(client, character_name, *TILE_B)

    assert response.status_code == 200, (
        f"expected 200 after move, got {response.status_code}: {response.text}"
    )

    position = get_position(client, character_name)
    assert position["x"] == TILE_B[0] and position["y"] == TILE_B[1], (
        f"expected position {TILE_B}, got {position}"
    )
    logger.info("position after move: %s", position)


def test_move_already_at_destination_returns_490(client, character_name):
    """
    Moving to the tile the character is already on must return 490.
    We move to TILE_B, wait for cooldown, then move there again — must get 490.
    """
    wait_for_cooldown(client, character_name)
    move_character(client, character_name, *TILE_B)

    wait_for_cooldown(client, character_name)
    response = move_character(client, character_name, *TILE_B)

    assert response.status_code == ALREADY_AT_DESTINATION, (
        f"expected 490 (already at destination), got {response.status_code}: {response.text}"
    )
    logger.info("repeated move to %s correctly returned 490", TILE_B)


def test_move_on_cooldown_returns_499(client, character_name):
    """
    Sending a move immediately after another move must return 499 (on cooldown).
    We wait for clean state, move to TILE_A, then immediately move to TILE_B
    without waiting — the second call must be rejected with 499.
    """
    wait_for_cooldown(client, character_name)
    first = move_character(client, character_name, *TILE_A)
    assert first.status_code == 200, (
        f"first move must succeed to set up cooldown, got {first.status_code}"
    )

    # No wait — fire immediately while cooldown is active
    second = move_character(client, character_name, *TILE_B)
    assert second.status_code == ON_COOLDOWN, (
        f"expected 499 (on cooldown), got {second.status_code}: {second.text}"
    )
    logger.info("immediate second move correctly returned 499")
