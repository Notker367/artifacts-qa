# Gathering tests for Artifacts MMO.
# Gathering requires the character to be on a tile with a gatherable resource.
# 497 = inventory full (valid — no space for gathered items).
# 499 = character on cooldown from a previous action.
# Tests do not sleep — cooldown is accepted as a valid outcome where applicable.

import logging

from services.errors import ON_COOLDOWN, INVENTORY_FULL
from services.movement import move_character
from services.gathering import gather, parse_gathered_items
from services.cooldown import parse_cooldown

logger = logging.getLogger(__name__)

# Known ash tree tile in the starting area.
# Update if the season map changes.
RESOURCE_TILE_X, RESOURCE_TILE_Y = 1, 1


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


def test_gather_returns_expected_status(client, character_name):
    """
    Gathering at the current position must return 200, 497, or 499.
    If the tile has no resource, the API may also return 598 (no resource here).
    All of these are valid game states — no unexpected failures should occur.
    """
    response = gather(client, character_name)

    # 598 = no resource on this tile; included as a valid outcome for smoke purposes
    VALID_GATHER_STATUSES = (200, INVENTORY_FULL, ON_COOLDOWN, 598)
    assert response.status_code in VALID_GATHER_STATUSES, (
        f"unexpected status {response.status_code}: {response.text}"
    )
    logger.info("gather at current tile: status=%d", response.status_code)


def test_gather_triggers_cooldown(client, character_name):
    """
    A successful gather (200) must include cooldown data in the response body.
    If we're already on cooldown, skip — we can't trigger a new action.
    """
    # Move to known resource tile first
    move_response = move_character(client, character_name, RESOURCE_TILE_X, RESOURCE_TILE_Y)
    if move_response.status_code == ON_COOLDOWN:
        logger.info("on cooldown before move — skipping cooldown check")
        return

    response = gather(client, character_name)
    if response.status_code != 200:
        logger.info("gather returned %d — cooldown check skipped", response.status_code)
        return

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
    We move to the resource tile, snapshot inventory, gather, compare.
    If cooldown or inventory full blocks us, log and skip the delta assertion.
    """
    move_response = move_character(client, character_name, RESOURCE_TILE_X, RESOURCE_TILE_Y)
    if move_response.status_code == ON_COOLDOWN:
        logger.info("on cooldown before move — skipping inventory delta check")
        return

    inventory_before = _get_inventory(client, character_name)
    logger.info("inventory before gather: %s", inventory_before)

    response = gather(client, character_name)
    logger.info("gather response: status=%d", response.status_code)

    if response.status_code in (ON_COOLDOWN, INVENTORY_FULL):
        logger.info("gather blocked (%d) — skipping delta check", response.status_code)
        return

    assert response.status_code == 200, (
        f"unexpected gather status: {response.status_code}: {response.text}"
    )

    gathered = parse_gathered_items(response)
    assert gathered, "successful gather must return at least one item"
    logger.info("gathered items: %s", gathered)

    inventory_after = _get_inventory(client, character_name)
    logger.info("inventory after gather: %s", inventory_after)

    # Each gathered item must appear in inventory with increased quantity
    for item in gathered:
        code = item["code"]
        qty_before = _find_item(inventory_before, code)
        qty_after = _find_item(inventory_after, code)
        assert qty_after > qty_before, (
            f"expected {code} quantity to increase: before={qty_before} after={qty_after}"
        )
        logger.info("%s: %d → %d (+%d)", code, qty_before, qty_after, qty_after - qty_before)


def test_gather_end_to_end(client, character_name):
    """
    End-to-end gathering flow: move to resource tile → gather → validate result.
    Verifies that the full sequence (location + action + state change) works together.
    If any step is blocked by cooldown, we log it and stop early — no failures.
    """
    # Step 1: move to the known resource tile
    move_response = move_character(client, character_name, RESOURCE_TILE_X, RESOURCE_TILE_Y)
    logger.info("move to resource tile (%d, %d): status=%d",
                RESOURCE_TILE_X, RESOURCE_TILE_Y, move_response.status_code)

    if move_response.status_code == ON_COOLDOWN:
        logger.info("blocked by cooldown at move step — end-to-end test incomplete")
        return

    assert move_response.status_code in (200, 490), (
        f"unexpected move status: {move_response.status_code}"
    )

    # Step 2: gather
    gather_response = gather(client, character_name)
    logger.info("gather: status=%d", gather_response.status_code)

    if gather_response.status_code == ON_COOLDOWN:
        logger.info("blocked by cooldown at gather step — end-to-end test incomplete")
        return

    if gather_response.status_code == INVENTORY_FULL:
        logger.info("inventory full — end-to-end test incomplete, deposit items first")
        return

    assert gather_response.status_code == 200, (
        f"unexpected gather status: {gather_response.status_code}: {gather_response.text}"
    )

    # Step 3: validate result
    gathered = parse_gathered_items(gather_response)
    cooldown = parse_cooldown(gather_response)

    assert gathered, "end-to-end gather must produce at least one item"
    assert cooldown is not None, "end-to-end gather must produce cooldown data"

    logger.info(
        "end-to-end gather complete: items=%s cooldown_remaining=%.1fs",
        gathered,
        cooldown.get("remaining_seconds", 0),
    )
