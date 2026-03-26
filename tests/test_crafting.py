# Crafting tests for Artifacts MMO.
# Crafting consumes materials and produces items at a workshop tile.
# Workshop is skill-specific — wrong tile returns 598 (no content here).
# All stateful tests call wait_for_cooldown before acting.
#
# Mining forge: (1, 5) — smelts copper_ore into copper bars (mining skill).
# Recipe: copper_ore × 10 → copper_bar × 1  (verified via GET /items/copper_bar).

import logging

from services.cooldown import wait_for_cooldown
from services.movement import move_character
from services.inventory import get_inventory, find_item, inventory_delta
from services.crafting import (
    craft,
    parse_craft_result,
    get_crafted_items,
    get_item_info,
    get_recipe,
    has_materials,
)
from services.errors import SKILL_LEVEL_TOO_LOW, ON_COOLDOWN, INVENTORY_FULL

logger = logging.getLogger(__name__)

# Mining forge tile — smelting workshop for ore → ingot conversion
MINING_FORGE_TILE = (1, 5)

# Target craft for end-to-end test
CRAFT_ITEM = "copper_bar"
MATERIAL_ITEM = "copper_ore"


# --- Data endpoint tests (no cooldown, no state changes) ---

def test_get_item_info_returns_data(client):
    """GET /items/copper_bar must return item metadata including craft field."""
    info = get_item_info(client, CRAFT_ITEM)
    assert info is not None, "copper_bar item info must not be None"
    assert "name" in info, "item info must have 'name'"
    assert "craft" in info, "copper_bar must have 'craft' field (it is craftable)"
    logger.info("item: %s | craft skill: %s | level: %s",
                info.get("name"),
                info.get("craft", {}).get("skill"),
                info.get("craft", {}).get("level"))


def test_get_recipe_returns_materials(client):
    """copper_bar recipe must list copper_ore as a required material."""
    info = get_item_info(client, CRAFT_ITEM)
    recipe = get_recipe(info)

    assert recipe, "copper_bar recipe must not be empty"

    codes = [m["code"] for m in recipe]
    assert MATERIAL_ITEM in codes, (
        f"copper_bar recipe must require {MATERIAL_ITEM!r}, got: {codes}"
    )

    ore_entry = next(m for m in recipe if m["code"] == MATERIAL_ITEM)
    assert ore_entry["quantity"] > 0, "required quantity must be > 0"
    logger.info("recipe: %s × %d → %s × 1",
                MATERIAL_ITEM, ore_entry["quantity"], CRAFT_ITEM)


def test_has_materials_logic():
    """has_materials must gate correctly on inventory contents — no API needed."""
    recipe = [{"code": "copper_ore", "quantity": 6}]
    inventory_enough = [{"code": "copper_ore", "quantity": 10}]
    inventory_short = [{"code": "copper_ore", "quantity": 3}]
    inventory_empty = []

    assert has_materials(inventory_enough, recipe), "10 ore satisfies recipe of 6"
    assert not has_materials(inventory_short, recipe), "3 ore does not satisfy recipe of 6"
    assert not has_materials(inventory_empty, recipe), "empty inventory fails"
    assert not has_materials(inventory_enough, []), "empty recipe returns False"

    # Quantity multiplier
    assert has_materials(inventory_enough, recipe, quantity=1), "qty=1 with 10 ore: ok"
    assert not has_materials(inventory_enough, recipe, quantity=2), (
        "qty=2 needs 12 ore, only have 10: fail"
    )
    logger.info("has_materials: all logic checks passed")


# --- Stateful tests (require workshop tile, cooldown wait) ---

def test_craft_copper_ingot_consumes_ore(client, character_name):
    """
    End-to-end craft flow: move to forge → craft 1 copper → verify ore consumed and copper gained.
    Character must have enough copper_ore in inventory (gathered beforehand or withdrawn from bank).
    Skips gracefully if materials are missing rather than failing the suite.
    """
    # Verify recipe first — use actual quantities from API, not hardcoded assumptions
    info = get_item_info(client, CRAFT_ITEM)
    recipe = get_recipe(info)
    assert recipe, "copper must have a recipe"

    wait_for_cooldown(client, character_name)
    inventory_before = get_inventory(client, character_name)
    ore_available = find_item(inventory_before, MATERIAL_ITEM)

    ore_needed = next(
        (m["quantity"] for m in recipe if m["code"] == MATERIAL_ITEM), 0
    )

    if ore_available < ore_needed:
        logger.warning(
            "skipping craft test: need %d %s, have %d",
            ore_needed, MATERIAL_ITEM, ore_available,
        )
        import pytest
        pytest.skip(f"not enough {MATERIAL_ITEM}: need {ore_needed}, have {ore_available}")

    # Move to the mining forge
    wait_for_cooldown(client, character_name)
    move_character(client, character_name, *MINING_FORGE_TILE)

    # Craft 1 copper ingot
    wait_for_cooldown(client, character_name)
    response = craft(client, character_name, CRAFT_ITEM, quantity=1)

    assert response.status_code == 200, (
        f"expected 200 from craft, got {response.status_code}: {response.text}"
    )

    result = parse_craft_result(response)
    assert result is not None, "craft response must contain parseable details"

    crafted = get_crafted_items(result)
    assert any(item["code"] == CRAFT_ITEM for item in crafted), (
        f"crafted items must include {CRAFT_ITEM!r}, got: {crafted}"
    )

    # Verify inventory delta: ore consumed, copper gained
    wait_for_cooldown(client, character_name)
    inventory_after = get_inventory(client, character_name)
    delta = inventory_delta(inventory_before, inventory_after)

    assert delta.get(MATERIAL_ITEM, 0) < 0, (
        f"{MATERIAL_ITEM} must be consumed by craft, delta={delta.get(MATERIAL_ITEM)}"
    )
    assert delta.get(CRAFT_ITEM, 0) > 0, (
        f"{CRAFT_ITEM} must appear in inventory after craft, delta={delta.get(CRAFT_ITEM)}"
    )

    xp = result.get("xp", 0)
    logger.info(
        "craft: %s → %s | ore consumed: %d | copper gained: %d | xp: %d",
        MATERIAL_ITEM,
        CRAFT_ITEM,
        abs(delta.get(MATERIAL_ITEM, 0)),
        delta.get(CRAFT_ITEM, 0),
        xp,
    )
