# Movement tests.
# Move is a POST action — it changes character location and triggers cooldown.
# 490 means the character is already at the target coordinates (valid game state).
# 499 means the character is still on cooldown from a previous action.

from services.errors import ALREADY_AT_DESTINATION, ON_COOLDOWN

VALID_MOVE_STATUSES = (200, ALREADY_AT_DESTINATION, ON_COOLDOWN)


def test_move_returns_expected_status(client, character_name):
    """
    Moving to coordinates (0, 1) should succeed or return a known game state code.
    We accept 490 (already there) and 499 (cooldown) as valid outcomes.
    """
    response = client.post(f"/my/{character_name}/action/move", json={"x": 0, "y": 1})
    assert response.status_code in VALID_MOVE_STATUSES
