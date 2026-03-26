# Combat tests.
# Fight is a POST action — it initiates combat with a monster at the character's location.
# The response includes fight result and cooldown data.
# 499 (cooldown) is an expected outcome, not a test failure.

from services.errors import ON_COOLDOWN

VALID_FIGHT_STATUSES = (200, ON_COOLDOWN)


def test_fight_returns_expected_status(client, character_name):
    """Fight should succeed or return 499 if the character is still on cooldown."""
    response = client.post(f"/my/{character_name}/action/fight")
    assert response.status_code in VALID_FIGHT_STATUSES


def test_fight_response_has_fight_data(client, character_name):
    """
    On a successful fight, the response body must contain 'fight' and 'cooldown' fields.
    These are used in downstream state transition checks.
    """
    response = client.post(f"/my/{character_name}/action/fight")
    if response.status_code == 200:
        data = response.json()["data"]
        assert "fight" in data
        assert "cooldown" in data
