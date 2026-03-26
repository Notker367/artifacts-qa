# Gathering tests for Artifacts MMO.
# Gathering requires the character to be on a tile with a gatherable resource.
# All stateful tests call wait_for_cooldown before acting so results are deterministic.
# 497 = inventory full (valid game state — no space for gathered items).
# 598 = no resource on this tile.

import logging

from services.errors import INVENTORY_FULL
from services.cooldown import wait_for_cooldown
from services.movement import move_character
from services.gathering import gather, parse_gathered_items
from services.cooldown import parse_cooldown

logger = logging.getLogger(__name__)

# Copper Rocks tile — skill: mining, level: 1, drops: copper_ore (+ rare gems).
# Map tile (2, 0), standard access. Update if the season map changes.
RESOURCE_TILE_X, RESOURCE_TILE_Y = 2, 0


def _get_inventory(client, character_name: str) -> list:
    """
    Read the character's current inventory from the server.
    Returns a list of {"code": str, "quantity": int} dicts.
    Temporary helper — will be replaced by services/inventory.py in item 9.
    """
    response = client.get(f"/characters/{character_name}")
    response.raise_for_status()
    return response.json()["data"].get("inventory", [])


def _find_item(inventory: list, code: str) -> int:
    """
    Return the total quantity of an item by code in the inventory list.
    Returns 0 if the item is not present.
    """
    return sum(slot["quantity"] for slot in inventory if slot["code"] == code)


def test_gather_returns_200_on_resource_tile(client, character_name):
    """
    Gathering on a known resource tile must return 200.
    We move to the resource tile first, wait for cooldown, then gather.
    """
    wait_for_cooldown(client, character_name)
    move_character(client, character_name, RESOURCE_TILE_X, RESOURCE_TILE_Y)

    wait_for_cooldown(client, character_name)
    response = gather(client, character_name)

    assert response.status_code == 200, (
        f"expected 200 on resource tile, got {response.status_code}: {response.text}"
    )
    logger.info("gather on resource tile: status=200")


def test_gather_triggers_cooldown(client, character_name):
    """
    A successful gather must include cooldown data in the response body.
    Cooldown is a mandatory game mechanic — any 200 gather response must carry it.
    """
    wait_for_cooldown(client, character_name)
    move_character(client, character_name, RESOURCE_TILE_X, RESOURCE_TILE_Y)

    wait_for_cooldown(client, character_name)
    response = gather(client, character_name)

    assert response.status_code == 200, (
        f"expected 200 to check cooldown, got {response.status_code}: {response.text}"
    )

    cooldown = parse_cooldown(response)
    assert cooldown is not None, "successful gather must include cooldown data"
    assert "remaining_seconds" in cooldown, "cooldown must include remaining_seconds"

    logger.info(
        "gather cooldown: remaining=%.1fs total=%ds",
        cooldown.get("remaining_seconds", 0),
        cooldown.get("total_time", 0),
    )


def test_gather_inventory_delta(client, character_name):
    """
    A successful gather must increase item quantity in the inventory.
    Snapshots inventory before, gathers, compares after — delta must be positive.
    """
    wait_for_cooldown(client, character_name)
    move_character(client, character_name, RESOURCE_TILE_X, RESOURCE_TILE_Y)

    wait_for_cooldown(client, character_name)
    inventory_before = _get_inventory(client, character_name)
    logger.info("inventory before gather: %s", inventory_before)

    response = gather(client, character_name)
    assert response.status_code == 200, (
        f"expected 200 for delta check, got {response.status_code}: {response.text}"
    )

    gathered = parse_gathered_items(response)
    assert gathered, "successful gather must return at least one item"

    inventory_after = _get_inventory(client, character_name)
    logger.info("gathered: %s", gathered)

    for item in gathered:
        code = item["code"]
        qty_before = _find_item(inventory_before, code)
        qty_after = _find_item(inventory_after, code)
        assert qty_after > qty_before, (
            f"{code}: expected quantity to increase, before={qty_before} after={qty_after}"
        )
        logger.info("%s: %d → %d (+%d)", code, qty_before, qty_after, qty_after - qty_before)


def test_gather_end_to_end(client, character_name):
    """
    End-to-end gathering flow: move to resource tile → gather → validate result and cooldown.
    Verifies that the full sequence (location + action + state change) works together.
    """
    wait_for_cooldown(client, character_name)
    move_response = move_character(client, character_name, RESOURCE_TILE_X, RESOURCE_TILE_Y)
    assert move_response.status_code in (200, 490), (
        f"unexpected move status: {move_response.status_code}"
    )
    logger.info("moved to resource tile (%d, %d)", RESOURCE_TILE_X, RESOURCE_TILE_Y)

    wait_for_cooldown(client, character_name)
    gather_response = gather(client, character_name)
    assert gather_response.status_code == 200, (
        f"expected 200 on gather, got {gather_response.status_code}: {gather_response.text}"
    )

    gathered = parse_gathered_items(gather_response)
    cooldown = parse_cooldown(gather_response)

    assert gathered, "end-to-end gather must produce at least one item"
    assert cooldown is not None, "end-to-end gather must produce cooldown data"

    logger.info(
        "end-to-end complete: items=%s cooldown_remaining=%.1fs",
        gathered,
        cooldown.get("remaining_seconds", 0),
    )
