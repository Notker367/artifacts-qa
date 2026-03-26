# Scenario manager for Artifacts MMO.
# Translates roles into action cycles and runs a dispatch loop over all characters.
#
# Design:
#   - ROLES dict: character name → role string (change one line to reassign)
#   - cycle functions: one full action cycle per role (move → act → post-check)
#   - dispatch loop: finds ready characters, runs their cycle, sleeps until next
#   - errors per character are logged and skipped — one broken char never stops the loop
#
# Resource tile placeholders (marked TODO) are filled in at task 18.1 (map discovery).

import logging
import time

from services.cooldown import wait_for_cooldown
from services.movement import move_character
from services.gathering import gather
from services.combat import fight, parse_fight_result, is_win
from services.rest import get_hp, rest
from services.inventory import get_inventory, free_slots
from services.bank import deposit_item, find_bank_item
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

# --- Known map tiles ---
MONSTER_TILE = (0, 1)          # Chicken, level 1 — combat target
BANK_TILE = (4, 1)             # nearest bank
MONSTERS_TASKMASTER_TILE = (1, 2)  # accept/complete monster tasks
MINING_TILE = (2, 0)           # Copper Rocks, mining level 1

# TODO (task 18.1): discover and fill in these tiles via GET /maps?content_type=resource
WOODCUTTING_TILE = None        # axe required — coordinates unknown
FISHING_TILE = None            # net required — coordinates unknown
ALCHEMY_TILE = None            # gloves required — coordinates unknown

# --- Thresholds ---
HP_THRESHOLD = 0.3     # rest when HP drops below 30% to avoid death penalty cooldown
DEPOSIT_THRESHOLD = 5  # deposit to bank when fewer than 5 free inventory slots remain


# --- Post-action helpers ---

def _maybe_rest(client, character_name: str) -> None:
    """Rest if HP is below threshold. Waits for cooldown before and after."""
    hp, max_hp = get_hp(client, character_name)
    if max_hp > 0 and hp / max_hp < HP_THRESHOLD:
        logger.info("%s: HP %.0f%% — resting", character_name, 100 * hp / max_hp)
        wait_for_cooldown(client, character_name)
        rest(client, character_name)


def _maybe_deposit_all(client, character_name: str) -> None:
    """
    Deposit all non-empty inventory items to bank if free slots are low.
    Moves to bank tile and back — caller must re-move to task tile after.
    """
    inventory = get_inventory(client, character_name)
    if free_slots(inventory) >= DEPOSIT_THRESHOLD:
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
    Only handles monster tasks — items tasks require a separate taskmaster tile.
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


# --- Cycle functions ---

def run_combat_cycle(client, character_name: str) -> None:
    """
    One combat action cycle:
      1. move to monster tile
      2. fight
      3. rest if HP below threshold
      4. complete + re-accept task if objective met
    """
    wait_for_cooldown(client, character_name)
    move_character(client, character_name, *MONSTER_TILE)

    wait_for_cooldown(client, character_name)
    response = fight(client, character_name)

    if response.status_code != 200:
        logger.warning("%s: fight returned %d", character_name, response.status_code)
        return

    result = parse_fight_result(response)
    outcome = "win" if result and is_win(result) else "loss"
    state = get_task_state(client, character_name)
    logger.info("%s: fight %s | task %s %d/%d",
                character_name, outcome,
                state["task"], state["task_progress"], state["task_total"])

    _maybe_rest(client, character_name)
    _maybe_complete_task(client, character_name)


def run_mining_cycle(client, character_name: str) -> None:
    """
    One mining action cycle:
      1. deposit if inventory is nearly full
      2. move to ore tile
      3. gather
    """
    _maybe_deposit_all(client, character_name)

    wait_for_cooldown(client, character_name)
    move_character(client, character_name, *MINING_TILE)

    wait_for_cooldown(client, character_name)
    response = gather(client, character_name)

    if response.status_code == 200:
        inventory = get_inventory(client, character_name)
        logger.info("%s: gathered | free slots: %d", character_name, free_slots(inventory))
    else:
        logger.warning("%s: gather returned %d", character_name, response.status_code)


def run_woodcutting_cycle(client, character_name: str) -> None:
    """
    One woodcutting action cycle.
    Tile coordinates not yet known — see task 18.1 (map discovery).
    """
    if WOODCUTTING_TILE is None:
        logger.error("%s: woodcutting tile not configured — skipping (see TODO 18.1)", character_name)
        return

    _maybe_deposit_all(client, character_name)

    wait_for_cooldown(client, character_name)
    move_character(client, character_name, *WOODCUTTING_TILE)

    wait_for_cooldown(client, character_name)
    response = gather(client, character_name)

    if response.status_code == 200:
        inventory = get_inventory(client, character_name)
        logger.info("%s: gathered | free slots: %d", character_name, free_slots(inventory))
    else:
        logger.warning("%s: gather returned %d", character_name, response.status_code)


def run_alchemy_cycle(client, character_name: str) -> None:
    """
    One alchemy/plant gathering action cycle.
    Tile coordinates not yet known — see task 18.1 (map discovery).
    """
    if ALCHEMY_TILE is None:
        logger.error("%s: alchemy tile not configured — skipping (see TODO 18.1)", character_name)
        return

    _maybe_deposit_all(client, character_name)

    wait_for_cooldown(client, character_name)
    move_character(client, character_name, *ALCHEMY_TILE)

    wait_for_cooldown(client, character_name)
    response = gather(client, character_name)

    if response.status_code == 200:
        inventory = get_inventory(client, character_name)
        logger.info("%s: gathered | free slots: %d", character_name, free_slots(inventory))
    else:
        logger.warning("%s: gather returned %d", character_name, response.status_code)


# --- Role dispatcher ---

_CYCLE_FUNCTIONS = {
    "combat":      run_combat_cycle,
    "mining":      run_mining_cycle,
    "woodcutting": run_woodcutting_cycle,
    "alchemy":     run_alchemy_cycle,
}


def run_cycle(client, character_name: str, role: str) -> None:
    """
    Run one action cycle for the given character based on their role.
    Unknown roles are logged and skipped without raising.
    """
    cycle_fn = _CYCLE_FUNCTIONS.get(role)
    if cycle_fn is None:
        logger.warning("%s: unknown role %r — skipping", character_name, role)
        return
    cycle_fn(client, character_name)


# --- Dispatch loop ---

def run_dispatch_loop(client, roles: dict = None, max_cycles: int = None) -> None:
    """
    Main dispatch loop. Runs indefinitely (or until max_cycles is reached).
    Each iteration:
      1. fetch all character states in one API call
      2. run one cycle for each character that is ready
      3. sleep exactly until the next character becomes available

    Errors per character are caught, logged, and skipped.
    One broken character never stops the loop.

    Args:
        client: ArtifactsClient instance
        roles: override ROLES dict (defaults to module-level ROLES)
        max_cycles: stop after this many total dispatch iterations (None = run forever)
    """
    active_roles = roles if roles is not None else ROLES
    cycle_count = 0

    logger.info("dispatch loop started | roles: %s", active_roles)

    while True:
        characters = get_all_characters(client)
        ready = find_ready_characters(characters)

        for char in ready:
            name = char["name"]
            role = active_roles.get(name)
            if not role:
                continue

            logger.info("--- %s [%s] ---", name, role)
            try:
                run_cycle(client, name, role)
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
