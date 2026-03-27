# Inventory helpers for Artifacts MMO.
# Inventory is a fixed-size list of slots — each slot has a code and quantity.
# Empty slots have code="" and quantity=0.
# Inventory size can be increased by equipping bags.

from services.errors import INVENTORY_FULL


def get_inventory(client, character_name: str) -> list:
    """
    Return the character's current inventory as a list of slot dicts.
    Each slot: {"slot": int, "code": str, "quantity": int}.
    Empty slots are included — use free_slots() to count available space.
    """
    response = client.get(f"/characters/{character_name}")
    response.raise_for_status()
    data = response.json()["data"]
    return data.get("inventory", [])


def get_inventory_max_items(client, character_name: str) -> int:
    """
    Return the character's total inventory capacity (number of slots).
    Increases when bags are equipped.
    """
    response = client.get(f"/characters/{character_name}")
    response.raise_for_status()
    return response.json()["data"].get("inventory_max_items", 0)


def get_inventory_state(client, character_name: str) -> tuple:
    """
    Return (inventory, max_items) from a single GET /characters call.
    Use this instead of calling get_inventory and get_inventory_max_items
    separately — avoids a redundant API request when both values are needed
    together (e.g. computing fill ratio before a deposit decision).
    """
    response = client.get(f"/characters/{character_name}")
    response.raise_for_status()
    data = response.json()["data"]
    return data.get("inventory", []), data.get("inventory_max_items", 100)


def free_slots(inventory: list) -> int:
    """
    Return the number of empty slots in the inventory.
    A slot is empty when its code is an empty string.
    """
    return sum(1 for slot in inventory if slot.get("code", "") == "")


def find_item(inventory: list, code: str) -> int:
    """
    Return the total quantity of an item by code across all inventory slots.
    Returns 0 if the item is not present.
    """
    return sum(slot["quantity"] for slot in inventory if slot.get("code") == code)


def inventory_delta(before: list, after: list) -> dict:
    """
    Compare two inventory snapshots and return quantity changes per item code.
    Returns a dict of {code: delta} for items whose quantity changed.
    Positive delta = gained, negative = lost.
    Useful for asserting that a gather, fight, or craft changed inventory as expected.
    """
    def totals(inventory):
        result = {}
        for slot in inventory:
            code = slot.get("code", "")
            if code:
                result[code] = result.get(code, 0) + slot["quantity"]
        return result

    before_totals = totals(before)
    after_totals = totals(after)

    all_codes = set(before_totals) | set(after_totals)
    return {
        code: after_totals.get(code, 0) - before_totals.get(code, 0)
        for code in all_codes
        if after_totals.get(code, 0) != before_totals.get(code, 0)
    }


def is_inventory_full(response) -> bool:
    """
    Return True if the API rejected an action because the inventory is full.
    497 is a normal game state — character needs to deposit items before continuing.
    """
    return response.status_code == INVENTORY_FULL
