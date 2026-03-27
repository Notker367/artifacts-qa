# Equipment helpers for Artifacts MMO.
# Equip/unequip actions do not require a specific tile — just POST /action/equip.
# The character must have the item in their inventory and not be on cooldown.

import logging

from services.character import EQUIPMENT_SLOTS

logger = logging.getLogger(__name__)

# Item type → equipment slot name.
# For slots that come in pairs (ring, artifact, utility), slot1 is preferred.
# The executor tries slot1 first; if a 422/conflict is returned, it falls back to slot2.
ITEM_TYPE_TO_SLOT: dict[str, str] = {
    "weapon":      "weapon_slot",
    "shield":      "shield_slot",
    "helmet":      "helmet_slot",
    "body_armor":  "body_armor_slot",
    "leg_armor":   "leg_armor_slot",
    "boots":       "boots_slot",
    "ring":        "ring1_slot",
    "amulet":      "amulet_slot",
    "artifact":    "artifact1_slot",
    "utility":     "utility1_slot",
    "bag":         "bag_slot",
    "tool":        "utility1_slot",  # tools (pickaxe, axe, fishing rod) use utility slot
    "resource":    None,             # resources are not equippable
    "consumable":  None,
}

# Fallback slots for dual-slot item types.
ITEM_TYPE_SLOT_FALLBACK: dict[str, str] = {
    "ring":     "ring2_slot",
    "artifact": "artifact2_slot",
    "utility":  "utility2_slot",
}


def get_slot_for_item(item_type: str, char: dict) -> str | None:
    """
    Return the equipment slot name for this item type.
    For paired slots (ring, artifact, utility): returns slot1 if empty, else slot2.
    Returns None if item type is not equippable.
    """
    primary = ITEM_TYPE_TO_SLOT.get(item_type)
    if primary is None:
        return None

    fallback = ITEM_TYPE_SLOT_FALLBACK.get(item_type)
    if fallback is None:
        return primary  # single-slot type

    # Use primary slot if it's empty, otherwise fall back to secondary
    if not char.get(primary, ""):
        return primary
    return fallback


def is_item_equipped(char: dict, item_code: str) -> bool:
    """Return True if item_code is currently equipped in any slot."""
    return any(char.get(slot, "") == item_code for slot in EQUIPMENT_SLOTS)


def equip_item(client, character_name: str, item_code: str, slot: str):
    """
    Equip item_code into the given slot.
    Character must have the item in inventory and not be on cooldown.
    Returns raw response — 200 on success, 491 if slot/item mismatch,
    499 if on cooldown, 485 if item already equipped.

    slot is the character field name (e.g. "weapon_slot"); the API expects
    the value without the _slot suffix (e.g. "weapon"), so we strip it here.
    """
    api_slot = slot.removesuffix("_slot")
    return client.post(
        f"/my/{character_name}/action/equip",
        json={"code": item_code, "slot": api_slot},
    )


def unequip_item(client, character_name: str, slot: str):
    """
    Unequip the item in slot and move it to inventory.
    slot is the character field name (e.g. "weapon_slot"); API expects "weapon".
    """
    api_slot = slot.removesuffix("_slot")
    return client.post(
        f"/my/{character_name}/action/unequip",
        json={"slot": api_slot},
    )
