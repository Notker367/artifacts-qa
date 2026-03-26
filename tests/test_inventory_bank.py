# Inventory and bank tests.
# Bank actions require the character to be at a bank location.
# 422 is expected if the character has no gold to deposit.
# 499 is expected if the character is on cooldown.

from services.errors import ON_COOLDOWN, UNPROCESSABLE

VALID_DEPOSIT_STATUSES = (200, ON_COOLDOWN, UNPROCESSABLE)


def test_deposit_gold_returns_expected_status(client, character_name):
    """
    Depositing 1 gold should succeed or return a known game state code.
    422 is valid when the character has no gold to deposit.
    """
    response = client.post(
        f"/my/{character_name}/action/bank/deposit/gold",
        json={"quantity": 1},
    )
    assert response.status_code in VALID_DEPOSIT_STATUSES


def test_get_bank_items_returns_200(client):
    """GET /my/bank/items should return 200 with a data envelope for an authenticated account."""
    response = client.get("/my/bank/items")
    assert response.status_code == 200
    assert "data" in response.json()
