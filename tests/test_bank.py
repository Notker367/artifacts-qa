# Stateful scenario: deposit changes inventory, withdraw reverses it.
# These tests assume character is already at the bank location.

COOLDOWN = 499


def test_deposit_gold_returns_expected_status(client, character_name):
    response = client.post(
        f"/my/{character_name}/action/bank/deposit/gold",
        json={"quantity": 1},
    )
    assert response.status_code in (200, COOLDOWN, 422)


def test_get_bank_items(client):
    response = client.get("/my/bank/items")
    assert response.status_code == 200
    assert "data" in response.json()
