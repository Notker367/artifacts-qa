# Move and fight actions.
# Most action endpoints return 499 if character is on cooldown — that's expected.

COOLDOWN = 499
ALREADY_AT_DESTINATION = 490


def test_move_returns_expected_status(client, character_name):
    response = client.post(f"/my/{character_name}/action/move", json={"x": 0, "y": 1})
    assert response.status_code in (200, ALREADY_AT_DESTINATION, COOLDOWN)


def test_fight_returns_expected_status(client, character_name):
    response = client.post(f"/my/{character_name}/action/fight")
    assert response.status_code in (200, COOLDOWN)


def test_fight_response_has_fight_data(client, character_name):
    response = client.post(f"/my/{character_name}/action/fight")
    if response.status_code == 200:
        data = response.json()["data"]
        assert "fight" in data
        assert "cooldown" in data
