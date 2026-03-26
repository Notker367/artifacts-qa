# Bank tests for Artifacts MMO.
# Bank actions require the character to be at a bank tile.
# Bank is account-level — items persist across sessions and characters.
# All stateful tests call wait_for_cooldown before acting.

import logging

from services.cooldown import wait_for_cooldown
from services.movement import move_character
from services.inventory import get_inventory, find_item
from services.bank import (
    get_bank_items,
    find_bank_item,
    bank_delta,
    deposit_item,
    withdraw_item,
    deposit_gold,
)
from services.errors import INSUFFICIENT_GOLD

logger = logging.getLogger(__name__)

# Nearest bank tile from the starting area.
BANK_TILE = (4, 1)
# Item reliably available from copper_rocks (2, 0) gathering.
DEPOSIT_ITEM = "copper_ore"
DEPOSIT_QTY = 1


def test_get_bank_items_structure(client):
    """
    GET /my/bank/items must return a list. Each item must have code and quantity.
    Bank is account-level — no character location required to read.
    """
    items = get_bank_items(client)

    assert isinstance(items, list), "bank items must be a list"
    for item in items:
        assert "code" in item, f"bank item missing 'code': {item}"
        assert "quantity" in item, f"bank item missing 'quantity': {item}"

    logger.info("bank contains %d item type(s)", len(items))


def test_deposit_item_changes_bank_state(client, character_name):
    """
    Depositing an item must increase its quantity in the bank.
    We move to the bank, snapshot bank state, deposit, compare delta.
    The character must have at least DEPOSIT_QTY of DEPOSIT_ITEM in inventory.
    """
    wait_for_cooldown(client, character_name)
    move_character(client, character_name, *BANK_TILE)

    # Ensure character has the item — if not, the deposit will 422 and the test will fail clearly
    inventory = get_inventory(client, character_name)
    qty_in_inventory = find_item(inventory, DEPOSIT_ITEM)
    assert qty_in_inventory >= DEPOSIT_QTY, (
        f"character needs at least {DEPOSIT_QTY} {DEPOSIT_ITEM} to deposit, "
        f"has {qty_in_inventory} — run gathering tests first"
    )

    bank_before = get_bank_items(client)
    logger.info("bank before deposit: %s in bank=%d", DEPOSIT_ITEM, find_bank_item(bank_before, DEPOSIT_ITEM))

    wait_for_cooldown(client, character_name)
    response = deposit_item(client, character_name, DEPOSIT_ITEM, DEPOSIT_QTY)

    assert response.status_code == 200, (
        f"expected 200 on deposit, got {response.status_code}: {response.text}"
    )

    bank_after = get_bank_items(client)
    delta = bank_delta(bank_before, bank_after)

    assert delta.get(DEPOSIT_ITEM, 0) == DEPOSIT_QTY, (
        f"expected bank delta +{DEPOSIT_QTY} for {DEPOSIT_ITEM}, got {delta}"
    )
    logger.info("bank delta after deposit: %s", delta)


def test_withdraw_item_changes_inventory(client, character_name):
    """
    Withdrawing an item must increase its quantity in the character's inventory.
    We move to bank, snapshot inventory, withdraw, compare delta.
    Requires at least DEPOSIT_QTY of DEPOSIT_ITEM in the bank.
    """
    wait_for_cooldown(client, character_name)
    move_character(client, character_name, *BANK_TILE)

    bank_items = get_bank_items(client)
    qty_in_bank = find_bank_item(bank_items, DEPOSIT_ITEM)
    assert qty_in_bank >= DEPOSIT_QTY, (
        f"bank needs at least {DEPOSIT_QTY} {DEPOSIT_ITEM} to withdraw, "
        f"has {qty_in_bank} — run test_deposit_item_changes_bank_state first"
    )

    inventory_before = get_inventory(client, character_name)
    logger.info("%s in inventory before withdraw: %d", DEPOSIT_ITEM, find_item(inventory_before, DEPOSIT_ITEM))

    wait_for_cooldown(client, character_name)
    response = withdraw_item(client, character_name, DEPOSIT_ITEM, DEPOSIT_QTY)

    assert response.status_code == 200, (
        f"expected 200 on withdraw, got {response.status_code}: {response.text}"
    )

    inventory_after = get_inventory(client, character_name)
    qty_before = find_item(inventory_before, DEPOSIT_ITEM)
    qty_after = find_item(inventory_after, DEPOSIT_ITEM)

    assert qty_after == qty_before + DEPOSIT_QTY, (
        f"{DEPOSIT_ITEM}: expected inventory {qty_before} → {qty_before + DEPOSIT_QTY}, got {qty_after}"
    )
    logger.info("%s inventory delta: %d → %d (+%d)", DEPOSIT_ITEM, qty_before, qty_after, DEPOSIT_QTY)


def test_deposit_gold_accepted_or_no_gold(client, character_name):
    """
    Depositing gold must return 200 (success) or 422 (character has no gold).
    Both are valid game states — we just verify no unexpected errors occur.
    Character gold is read first so we can log context.
    """
    wait_for_cooldown(client, character_name)
    move_character(client, character_name, *BANK_TILE)

    # Read character gold for context
    char_data = client.get(f"/characters/{character_name}").json()["data"]
    gold = char_data.get("gold", 0)
    logger.info("character gold: %d", gold)

    wait_for_cooldown(client, character_name)
    response = deposit_gold(client, character_name, 1)

    assert response.status_code in (200, INSUFFICIENT_GOLD), (
        f"unexpected status on gold deposit: {response.status_code}: {response.text}"
    )
    logger.info("gold deposit: status=%d", response.status_code)
