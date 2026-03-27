# Scenario manager for Artifacts MMO.
# Translates roles into action cycles and runs a dispatch loop over all characters.
#
# Design:
#   - ROLES dict: character name → role string (change one line to reassign)
#   - ROLE_RESOURCE dict: role → content_code — no hardcoded coordinates
#   - _resolve_tile: looks up (x, y) from cache at call time using the content code
#   - cycle functions: one full action cycle per role (move → act → post-check)
#   - dispatch loop: builds cache once per iteration, runs ready characters, sleeps until next
#   - errors per character are logged and skipped — one broken char never stops the loop
#
# To change which tile a role targets: edit ROLE_RESOURCE, not coordinates.
# To change which character does what: edit ROLES, not cycle logic.

import logging
import time

from services.cooldown import wait_for_cooldown
from services.movement import move_character
from services.gathering import gather
from services.combat import fight, parse_fight_result, is_win
from services.rest import get_hp, rest
from services.inventory import get_inventory, free_slots
from services.errors import INVENTORY_FULL
from services.bank import deposit_item, find_bank_item
from services.map_cache import get_map_cache, find_content
from services.tasks import (
    get_task_state,
    has_active_task,
    is_task_complete,
    accept_task,
    complete_task,
)
from services.multi_char import (
    get_all_characters,
    find_ready_characters,
    sleep_until_next_ready,
)

logger = logging.getLogger(__name__)

# --- Role assignment ---
# One line per character. Change the value to reassign a role.
ROLES = {
    "Furiba":     "combat",
    "Fussat":     "combat",
    "Velikossat": "woodcutting",
    "Ognerot":    "mining",
    "Mikrochelo": "alchemy",
}

# --- Role → content code ---
# These are content_code values from the map cache, not coordinates.
# Tile coordinates are resolved at runtime via _resolve_tile.
# To target a different resource or monster: change the code here.
ROLE_RESOURCE = {
    "combat":      "chicken",         # monster, level 1
    "mining":      "copper_rocks",    # resource, mining level 1
    "woodcutting": "ash_tree",        # resource, woodcutting level 1
    "fishing":     "gudgeon_spot",    # resource, fishing level 1
    "alchemy":     "sunflower_field", # resource, alchemy level 1
}

# --- Fixed infrastructure tiles ---
# These are NPC/building tiles that don't belong to a gathering role.
# They stay hardcoded because they are stable map features, not targets.
BANK_TILE = (4, 1)                    # nearest bank from starting area
MONSTERS_TASKMASTER_TILE = (1, 2)     # accept/complete monster tasks

# --- Thresholds ---
HP_THRESHOLD = 0.3     # rest when HP drops below 30% to avoid death penalty cooldown
DEPOSIT_THRESHOLD = 5  # deposit to bank when fewer than 5 free inventory slots remain


# ---------------------------------------------------------------------------
# Tile resolver
# ---------------------------------------------------------------------------

def _resolve_tile(cache: dict, code: str) -> tuple | None:
    """
    Return (x, y) of the first tile with this content_code.
    Works for any content type — resource, monster, workshop, etc.
    Logs an error and returns None if the code is not found in the cache.
    A None result signals the caller to skip the cycle rather than crash.
    """
    tiles = find_content(cache, code)
    if not tiles:
        logger.error("_resolve_tile: no tile found for %r — cache may be stale", code)
        return None
    return (tiles[0]["x"], tiles[0]["y"])


# ---------------------------------------------------------------------------
# Post-action helpers
# ---------------------------------------------------------------------------

def _maybe_rest(client, character_name: str) -> None:
    """Rest if HP is below threshold. Waits for cooldown before and after."""
    hp, max_hp = get_hp(client, character_name)
    if max_hp > 0 and hp / max_hp < HP_THRESHOLD:
        logger.info("%s: HP %.0f%% — resting", character_name, 100 * hp / max_hp)
        wait_for_cooldown(client, character_name)
        rest(client, character_name)


def _maybe_deposit_all(client, character_name: str, force: bool = False) -> None:
    """
    Deposit all non-empty inventory items to bank if free slots are low.
    Moves to bank tile and back — caller must re-move to task tile after.

    force=True skips the free_slots threshold check and deposits unconditionally.
    Use this when gather returns 497 (INVENTORY_FULL): free_slots counts empty slot
    entries but inventory_max_items is a quantity limit — characters can have many
    empty slots yet still be at max item count.
    """
    inventory = get_inventory(client, character_name)
    if not force and free_slots(inventory) >= DEPOSIT_THRESHOLD:
        return

    logger.info("%s: inventory low (%d free) — depositing to bank", character_name, free_slots(inventory))
    wait_for_cooldown(client, character_name)
    move_character(client, character_name, *BANK_TILE)

    for slot in inventory:
        code = slot.get("code", "")
        qty = slot.get("quantity", 0)
        if code and qty > 0:
            wait_for_cooldown(client, character_name)
            deposit_item(client, character_name, code, qty)
            logger.info("%s: deposited %s × %d", character_name, code, qty)


def _maybe_complete_task(client, character_name: str) -> None:
    """
    If the character's task is complete, go to taskmaster, turn it in, accept a new one.
    Only handles monster tasks — item tasks require a separate taskmaster tile.
    """
    state = get_task_state(client, character_name)
    if not has_active_task(state) or not is_task_complete(state):
        return

    logger.info("%s: task complete (%s %d/%d) — turning in",
                character_name, state["task"], state["task_progress"], state["task_total"])

    wait_for_cooldown(client, character_name)
    move_character(client, character_name, *MONSTERS_TASKMASTER_TILE)

    wait_for_cooldown(client, character_name)
    response = complete_task(client, character_name)
    if response.status_code == 200:
        logger.info("%s: task reward received", character_name)
    else:
        logger.warning("%s: complete_task unexpected status %d", character_name, response.status_code)
        return

    # Accept next task immediately
    wait_for_cooldown(client, character_name)
    response = accept_task(client, character_name)
    if response.status_code == 200:
        state = get_task_state(client, character_name)
        logger.info("%s: new task accepted — %s × %d",
                    character_name, state["task"], state["task_total"])
    else:
        logger.warning("%s: accept_task unexpected status %d", character_name, response.status_code)


# ---------------------------------------------------------------------------
# Cycle functions
# ---------------------------------------------------------------------------

def _hp_from_fight_response(response, character_name: str) -> tuple:
    """
    Extract (hp, max_hp) for this character from the fight response.
    The fight response includes data.characters[] with the full post-fight state.
    Avoids a separate GET /characters call just to read HP after combat.
    Returns (None, None) if not parseable.
    """
    try:
        for char in response.json()["data"]["characters"]:
            if char.get("name") == character_name:
                return char.get("hp"), char.get("max_hp")
    except (KeyError, TypeError, ValueError):
        pass
    return None, None


def run_combat_cycle(client, character_name: str, cache: dict) -> None:
    """
    One combat action cycle:
      1. rest if HP is low — BEFORE moving to monster tile
         (after a death, character respawns at spawn point with 1 HP;
          without this check the next cycle walks them into combat at 1 HP)
      2. move to monster tile
      3. fight
      4. rest again if HP dropped below threshold during the fight
      5. complete + re-accept task if objective met
    """
    # Pre-fight HP check: must happen before movement so a dead/damaged
    # character doesn't walk into the next fight before recovering.
    wait_for_cooldown(client, character_name)
    _maybe_rest(client, character_name)

    tile = _resolve_tile(cache, ROLE_RESOURCE["combat"])
    if tile is None:
        return

    wait_for_cooldown(client, character_name)
    move_character(client, character_name, *tile)

    wait_for_cooldown(client, character_name)
    response = fight(client, character_name)

    if response.status_code != 200:
        logger.warning("%s: fight returned %d", character_name, response.status_code)
        return

    result = parse_fight_result(response)
    outcome = "win" if result and is_win(result) else "loss"

    # Read post-fight HP from the response — no extra API call needed.
    hp, max_hp = _hp_from_fight_response(response, character_name)
    hp_str = f"{hp}/{max_hp}" if hp is not None else "?"

    state = get_task_state(client, character_name)
    logger.info("%s: fight %s | HP %s | task %s %d/%d",
                character_name, outcome, hp_str,
                state["task"], state["task_progress"], state["task_total"])

    # Post-fight HP check: handles surviving fights with heavy damage taken.
    _maybe_rest(client, character_name)
    _maybe_complete_task(client, character_name)


def _run_gathering_cycle(client, character_name: str, cache: dict, role: str) -> None:
    """
    Generic gathering cycle used by mining, woodcutting, fishing, alchemy.
    Resolves tile from cache using the role's content code.
      1. deposit if inventory is nearly full
      2. move to resource tile
      3. gather
    """
    tile = _resolve_tile(cache, ROLE_RESOURCE[role])
    if tile is None:
        return

    _maybe_deposit_all(client, character_name)

    wait_for_cooldown(client, character_name)
    move_character(client, character_name, *tile)

    wait_for_cooldown(client, character_name)
    response = gather(client, character_name)

    if response.status_code == 200:
        inventory = get_inventory(client, character_name)
        logger.info("%s: gathered | free slots: %d", character_name, free_slots(inventory))
    elif response.status_code == INVENTORY_FULL:
        # Inventory is full by quantity (inventory_max_items), not necessarily by slot count.
        # free_slots() counts empty slot entries — may be high even when quantity is maxed.
        # Force deposit bypasses the threshold check so we always clear the inventory here.
        logger.info("%s: inventory full (497) — forcing deposit to bank", character_name)
        _maybe_deposit_all(client, character_name, force=True)
    else:
        logger.warning("%s: gather returned %d", character_name, response.status_code)


def run_mining_cycle(client, character_name: str, cache: dict) -> None:
    """Mining cycle — targets ROLE_RESOURCE['mining'] (default: copper_rocks)."""
    _run_gathering_cycle(client, character_name, cache, "mining")


def run_woodcutting_cycle(client, character_name: str, cache: dict) -> None:
    """Woodcutting cycle — targets ROLE_RESOURCE['woodcutting'] (default: ash_tree)."""
    _run_gathering_cycle(client, character_name, cache, "woodcutting")


def run_fishing_cycle(client, character_name: str, cache: dict) -> None:
    """Fishing cycle — targets ROLE_RESOURCE['fishing'] (default: gudgeon_spot)."""
    _run_gathering_cycle(client, character_name, cache, "fishing")


def run_alchemy_cycle(client, character_name: str, cache: dict) -> None:
    """Alchemy cycle — targets ROLE_RESOURCE['alchemy'] (default: sunflower_field)."""
    _run_gathering_cycle(client, character_name, cache, "alchemy")


# ---------------------------------------------------------------------------
# Role dispatcher
# ---------------------------------------------------------------------------

_CYCLE_FUNCTIONS = {
    "combat":      run_combat_cycle,
    "mining":      run_mining_cycle,
    "woodcutting": run_woodcutting_cycle,
    "fishing":     run_fishing_cycle,
    "alchemy":     run_alchemy_cycle,
}


def run_cycle(client, character_name: str, role: str, cache: dict) -> None:
    """
    Run one action cycle for the given character based on their role.
    Unknown roles are logged and skipped without raising.
    """
    cycle_fn = _CYCLE_FUNCTIONS.get(role)
    if cycle_fn is None:
        logger.warning("%s: unknown role %r — skipping", character_name, role)
        return
    cycle_fn(client, character_name, cache)


# ---------------------------------------------------------------------------
# Dispatch loop
# ---------------------------------------------------------------------------

def run_dispatch_loop(client, roles: dict = None, max_cycles: int = None) -> None:
    """
    Main dispatch loop. Runs indefinitely (or until max_cycles is reached).
    Each iteration:
      1. load or refresh the map cache (fetches from API only when stale)
      2. fetch all character states in one API call
      3. run one cycle for each character that is ready
      4. sleep exactly until the next character becomes available

    Errors per character are caught, logged, and skipped.
    One broken character never stops the loop.

    Args:
        client:     ArtifactsClient instance
        roles:      override ROLES dict (defaults to module-level ROLES)
        max_cycles: stop after this many total dispatch iterations (None = run forever)
    """
    active_roles = roles if roles is not None else ROLES
    cycle_count = 0

    logger.info("dispatch loop started | roles: %s", active_roles)

    while True:
        # Cache is loaded once per iteration — fresh file read, no API call unless stale
        cache = get_map_cache(client)

        characters = get_all_characters(client)
        ready = find_ready_characters(characters)

        for char in ready:
            name = char["name"]
            role = active_roles.get(name)
            if not role:
                continue

            logger.info("--- %s [%s] ---", name, role)
            try:
                run_cycle(client, name, role, cache)
            except Exception as exc:
                logger.error("%s: cycle failed — %s: %s", name, type(exc).__name__, exc)

        cycle_count += 1
        if max_cycles is not None and cycle_count >= max_cycles:
            logger.info("dispatch loop: reached max_cycles=%d, stopping", max_cycles)
            break

        # Refresh character states after acting and compute sleep time
        characters = get_all_characters(client)
        wait = sleep_until_next_ready(characters)
        if wait > 0:
            logger.info("dispatch: sleeping %.1fs until next character is ready", wait)
            time.sleep(wait)
