# Bank helpers for Artifacts MMO.
# Bank actions require the character to be at a bank tile.
# Bank stores items and gold at the account level — shared across characters.


def get_bank_items(client) -> list:
    """
    Return all items currently stored in the account bank.
    Uses GET /my/bank/items — auth required, no character location needed.
    Returns a list of {"code": str, "quantity": int} dicts.
    """
    response = client.get("/my/bank/items")
    response.raise_for_status()
    return response.json().get("data", [])


def find_bank_item(bank_items: list, code: str) -> int:
    """
    Return the total quantity of an item by code in the bank.
    Returns 0 if the item is not present.
    """
    return sum(item["quantity"] for item in bank_items if item.get("code") == code)


def bank_delta(before: list, after: list) -> dict:
    """
    Compare two bank item snapshots and return quantity changes per code.
    Returns {code: delta} for items whose quantity changed.
    Positive = deposited, negative = withdrawn.
    Mirrors inventory_delta from services/inventory.py — same logic, different data source.
    """
    def totals(items):
        result = {}
        for item in items:
            code = item.get("code", "")
            if code:
                result[code] = result.get(code, 0) + item["quantity"]
        return result

    before_totals = totals(before)
    after_totals = totals(after)

    all_codes = set(before_totals) | set(after_totals)
    return {
        code: after_totals.get(code, 0) - before_totals.get(code, 0)
        for code in all_codes
        if after_totals.get(code, 0) != before_totals.get(code, 0)
    }


def deposit_item(client, character_name: str, code: str, quantity: int):
    """
    Deposit items from character inventory into the bank.
    Character must be at a bank tile. Returns raw response.
    API expects a list payload — allows batching, but we deposit one item at a time here.
    Endpoint: POST /my/{name}/action/bank/deposit/item
    """
    return client.post(
        f"/my/{character_name}/action/bank/deposit/item",
        json=[{"code": code, "quantity": quantity}],
    )


def withdraw_item(client, character_name: str, code: str, quantity: int):
    """
    Withdraw items from the bank into character inventory.
    Character must be at a bank tile. Returns raw response.
    API expects a list payload — allows batching, but we withdraw one item at a time here.
    Endpoint: POST /my/{name}/action/bank/withdraw/item
    """
    return client.post(
        f"/my/{character_name}/action/bank/withdraw/item",
        json=[{"code": code, "quantity": quantity}],
    )


def deposit_gold(client, character_name: str, quantity: int):
    """
    Deposit gold from character into the bank.
    Returns 422 if the character does not have enough gold.
    """
    return client.post(
        f"/my/{character_name}/action/bank/deposit/gold",
        json={"quantity": quantity},
    )


def withdraw_gold(client, character_name: str, quantity: int):
    """
    Withdraw gold from the bank to the character.
    Returns 422 if the bank does not have enough gold.
    """
    return client.post(
        f"/my/{character_name}/action/bank/withdraw/gold",
        json={"quantity": quantity},
    )
