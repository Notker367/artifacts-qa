# Inventory tests for Artifacts MMO.
# Inventory is a fixed-size slot list — empty slots have code="".
# 497 = inventory full — tested as a long scenario (requires filling all slots).
# All stateful tests call wait_for_cooldown before actions.

import logging
import pytest

from services.cooldown import wait_for_cooldown
from services.movement import move_character
from services.gathering import gather
from services.inventory import (
    get_inventory,
    get_inventory_max_items,
    free_slots,
    find_item,
    inventory_delta,
    is_inventory_full,
)

logger = logging.getLogger(__name__)

# Copper Rocks tile — mining level 1, drops copper_ore.
RESOURCE_TILE = (2, 0)
# Item reliably dropped at the resource tile above.
EXPECTED_ITEM = "copper_ore"


def test_get_inventory_returns_list(client, character_name):
    """
    GET /characters/{name} must return an inventory list with slot dicts.
    Each slot must have the keys: slot, code, quantity.
    """
    inventory = get_inventory(client, character_name)

    assert isinstance(inventory, list), "inventory must be a list"
    assert len(inventory) > 0, "inventory must have at least one slot"

    for slot in inventory:
        assert "slot" in slot, f"slot dict missing 'slot' key: {slot}"
        assert "code" in slot, f"slot dict missing 'code' key: {slot}"
        assert "quantity" in slot, f"slot dict missing 'quantity' key: {slot}"

    logger.info("inventory: %d slots total", len(inventory))


def test_inventory_max_items(client, character_name):
    """
    inventory_max_items is the account-level maximum capacity (expandable via bags).
    The API returns only the currently active slots — their count may be lower.
    We assert that max_items is a positive int and >= the active slot count.
    """
    inventory = get_inventory(client, character_name)
    max_items = get_inventory_max_items(client, character_name)

    assert isinstance(max_items, int) and max_items > 0, (
        f"inventory_max_items must be a positive int, got {max_items}"
    )
    assert max_items >= len(inventory), (
        f"inventory_max_items {max_items} is less than active slot count {len(inventory)}"
    )
    logger.info("active slots: %d, account max: %d", len(inventory), max_items)


def test_free_slots_count(client, character_name):
    """
    free_slots must return a non-negative count that does not exceed total capacity.
    """
    inventory = get_inventory(client, character_name)
    max_items = get_inventory_max_items(client, character_name)
    empty = free_slots(inventory)

    assert 0 <= empty <= max_items, (
        f"free_slots={empty} out of range [0, {max_items}]"
    )
    logger.info("free slots: %d / %d", empty, max_items)


def test_find_item_returns_correct_quantity(client, character_name):
    """
    find_item must return the correct total quantity for a present item
    and 0 for an item that does not exist in the inventory.
    """
    inventory = get_inventory(client, character_name)

    # Unknown item must return 0
    assert find_item(inventory, "this_item_does_not_exist") == 0

    # For any item actually in inventory, find_item must match the slot quantity
    for slot in inventory:
        if slot["code"]:
            expected = slot["quantity"]
            found = find_item(inventory, slot["code"])
            assert found >= expected, (
                f"find_item({slot['code']}) returned {found}, expected >= {expected}"
            )
            logger.info("find_item(%s) = %d", slot["code"], found)
            break


def test_inventory_delta_after_gather(client, character_name):
    """
    inventory_delta must detect the quantity change produced by a gather action.
    We snapshot inventory, gather once, compare — delta must show a gain.
    """
    wait_for_cooldown(client, character_name)
    move_character(client, character_name, *RESOURCE_TILE)

    wait_for_cooldown(client, character_name)
    before = get_inventory(client, character_name)

    response = gather(client, character_name)
    assert response.status_code == 200, (
        f"expected 200 from gather, got {response.status_code}: {response.text}"
    )

    after = get_inventory(client, character_name)
    delta = inventory_delta(before, after)

    assert delta, "inventory delta must not be empty after a successful gather"
    assert any(v > 0 for v in delta.values()), (
        f"expected at least one positive delta after gather, got {delta}"
    )
    logger.info("inventory delta after gather: %s", delta)


@pytest.mark.long
def test_inventory_full_returns_497(client, character_name):
    """
    When the inventory is full, gather must return 497.
    We gather repeatedly until 497 is returned or slots run out.
    This test is marked long — it may take several minutes of cooldown cycles.
    """
    wait_for_cooldown(client, character_name)
    move_character(client, character_name, *RESOURCE_TILE)

    max_attempts = get_inventory_max_items(client, character_name) + 5
    got_497 = False

    for attempt in range(max_attempts):
        wait_for_cooldown(client, character_name)
        inventory = get_inventory(client, character_name)
        empty = free_slots(inventory)
        logger.info("attempt %d: free slots=%d", attempt + 1, empty)

        response = gather(client, character_name)

        if is_inventory_full(response):
            logger.info("got 497 (inventory full) after %d gathers", attempt + 1)
            got_497 = True
            break

        assert response.status_code == 200, (
            f"unexpected gather status: {response.status_code}: {response.text}"
        )

    assert got_497, (
        f"inventory full (497) was never triggered after {max_attempts} gathers"
    )
