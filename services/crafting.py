# Crafting helpers for Artifacts MMO.
# Crafting is a POST action that consumes materials and produces items.
# The character must be at the correct workshop tile for the target item's skill.
# Workshop type is per-skill: mining, weaponcrafting, gearcrafting, jewelrycrafting, cooking, alchemy.
#
# Known workshop tiles:
#   (1, 5) — mining forge (smelting ores into bars, mining skill)
#            e.g. copper_ore × 10 → copper_bar × 1


def craft(client, character_name: str, item_code: str, quantity: int = 1):
    """
    Perform a crafting action at the current tile.
    Character must be at the correct workshop for the item's skill.
    Returns raw response — 200 on success, 499 on cooldown, 493 if skill too low,
    497 if inventory full, 598 if no workshop on this tile.
    """
    return client.post(
        f"/my/{character_name}/action/crafting",
        json={"code": item_code, "quantity": quantity},
    )


def parse_craft_result(response) -> dict | None:
    """
    Extract the craft result block from a successful crafting response.
    Returns data.details dict with: xp, items (list of crafted items).
    Returns None if not present (e.g. error response).
    """
    try:
        return response.json()["data"]["details"]
    except (KeyError, TypeError, ValueError):
        return None


def get_crafted_items(craft_result: dict) -> list:
    """
    Return the list of items produced by the craft.
    Each entry: {"code": str, "quantity": int}.
    Returns empty list if craft_result is None or has no items.
    """
    if not craft_result:
        return []
    return craft_result.get("items", [])


def get_item_info(client, item_code: str) -> dict | None:
    """
    Fetch item metadata from GET /items/{code}.
    Returns the data dict which includes: name, type, level, craft requirements.
    Returns None if item not found (404).
    """
    response = client.get(f"/items/{item_code}")
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json().get("data")


def get_recipe(item_info: dict) -> list:
    """
    Extract the crafting recipe from item metadata.
    Returns a list of {"code": str, "quantity": int} — materials needed for one craft.
    Returns empty list if item has no recipe (not craftable).
    """
    if not item_info:
        return []
    craft = item_info.get("craft") or {}
    return craft.get("items", [])


def has_materials(inventory: list, recipe: list, quantity: int = 1) -> bool:
    """
    Return True if the inventory contains enough materials for the given recipe × quantity.
    Works on already-fetched inventory and recipe — makes no API calls.
    Use before crafting to guard against missing-material failures.
    """
    if not recipe:
        return False

    # Build a flat {code: total_quantity} map from inventory
    totals: dict[str, int] = {}
    for slot in inventory:
        code = slot.get("code", "")
        if code:
            totals[code] = totals.get(code, 0) + slot.get("quantity", 0)

    for material in recipe:
        needed = material["quantity"] * quantity
        if totals.get(material["code"], 0) < needed:
            return False

    return True
