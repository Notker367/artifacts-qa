#!/usr/bin/env python3
"""
Goals runner for Artifacts MMO.

Runs a planner → assign → execute loop. Unlike scripts/farm.py (which farms
forever based on fixed roles), this runner works toward specific user-defined
goals: collect N items, craft N items, equip a character, level a skill.

Usage:
    python scripts/goals.py                  # run until all goals complete
    python scripts/goals.py --cycles 10      # stop after 10 dispatch iterations

Adding goals:
    Edit the GOALS list at the bottom of this file.
    Each goal is created with a shorthand constructor:

        Goal.collect("copper_ore", 200)
        Goal.collect("ash_wood", 100, allowed_characters=["Velikossat"])
        Goal.level("mining", 10, "Ognerot")

Goals are stored in data/goals.db. If a goal with the same parameters
already exists and is active, it will not be duplicated — the planner is
idempotent. To reset all goals, delete data/goals.db and restart.

Loop flow per iteration:
    1. run_planning_cycle  — creates/updates tasks based on goal state
    2. build_world_state   — one fresh snapshot (3 API calls)
    3. for each ready character: find best open task → claim → execute
    4. sleep until next character is ready
"""

import argparse
import logging
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from clients.artifacts_client import ArtifactsClient
from services.cooldown import wait_for_cooldown
from services.movement import move_character, get_position
from services.gathering import gather
from services.combat import fight, parse_fight_result, is_win
from services.rest import get_hp, rest
from services.inventory import get_inventory_state, find_item
from services.bank import deposit_item, withdraw_item
from services.crafting import craft as craft_action
from services.multi_char import find_ready_characters, get_all_characters, sleep_until_next_ready
from services.map_cache import find_content
from services.item_data import resource_for_item, workshop_code_for_skill
from services.item_cache import get_cached_recipe, get_craft_skill
from services.equipment import equip_item, get_slot_for_item, is_item_equipped
from services.character import EQUIPMENT_SLOTS
from services.goal_store import (
    init_db,
    insert_goal,
    get_goals,
    get_tasks,
    update_task_status,
    release_reservations_for_task,
    claim_task,
)
from services.goals import Goal, GoalStatus, TaskStatus, TaskType
from services.world_state import build_world_state
from services.planner import run_planning_cycle
from services.assignment import find_best_task_for_character, find_best_character_for_task
from services.errors import INVENTORY_FULL

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("goals")

# Bank tile for deposits — same as scenario.py
BANK_TILE = (4, 1)


# ---------------------------------------------------------------------------
# Goal definitions — edit this list to set your goals
# ---------------------------------------------------------------------------

GOALS: list[Goal] = [
    Goal.equip("copper_dagger", "Furiba"),
]


# ---------------------------------------------------------------------------
# Task executor — one executor per task type
# ---------------------------------------------------------------------------

def _resolve_resource_tile(task: dict, cache: dict) -> tuple | None:
    """
    Return (x, y) of the resource tile for a gather task.
    task.item_code is a drop code (e.g. "copper_ore"); we look up the
    resource content_code ("copper_rocks") and find its tile in the cache.
    """
    item_code = task.get("item_code")
    resource_code = resource_for_item(item_code)
    if not resource_code:
        logger.error("executor: no resource mapping for %r", item_code)
        return None
    tiles = find_content(cache, resource_code)
    if not tiles:
        logger.error("executor: no tile in cache for %r", resource_code)
        return None
    return tiles[0]["x"], tiles[0]["y"]


def _deposit_all_to_bank(client, char_name: str, inventory: list) -> None:
    """
    Move to bank and deposit all non-empty inventory slots.
    Leaves the character at the bank tile — caller moves back to resource.
    """
    wait_for_cooldown(client, char_name)
    move_character(client, char_name, *BANK_TILE)
    for slot in inventory:
        code = slot.get("code", "")
        qty = slot.get("quantity", 0)
        if code and qty > 0:
            wait_for_cooldown(client, char_name)
            deposit_item(client, char_name, code, qty)
            logger.info("executor: %s deposited %s × %d", char_name, code, qty)


def execute_gather_task(client, char_name: str, task: dict, cache: dict) -> None:
    """
    Execute a gather task: move to resource tile, gather until target quantity
    is reached or inventory fills, then deposit to bank.

    A gather task has a `quantity` field (e.g. 80 copper_ore). The executor
    loops gather actions until the character has accumulated that many of the
    target item in their inventory — then deposits and marks the task done.

    Safety cap: 100 gather actions per task to prevent infinite loops on
    unexpected game states (e.g. resource depleted, item not dropping).
    """
    item_code  = task["item_code"]
    target_qty = task["quantity"]
    task_id    = task["id"]

    tile = _resolve_resource_tile(task, cache)
    if tile is None:
        update_task_status(task_id, TaskStatus.FAILED, "could not resolve resource tile")
        return

    gathered = 0
    MAX_ACTIONS = 100

    for attempt in range(MAX_ACTIONS):
        inventory, max_items = get_inventory_state(client, char_name)
        current_in_inv = find_item(inventory, item_code)

        # Done condition: gathered enough of this item
        if current_in_inv >= target_qty:
            logger.info(
                "executor: %s reached target %d %s — depositing",
                char_name, target_qty, item_code,
            )
            _deposit_all_to_bank(client, char_name, inventory)
            break

        # Proactive deposit: inventory quantity nearing the limit
        total_qty = sum(s.get("quantity", 0) for s in inventory)
        if total_qty >= max_items * 0.8:
            logger.info("executor: %s inventory at %.0f%% — depositing early", char_name, 100 * total_qty / max_items)
            _deposit_all_to_bank(client, char_name, inventory)
            # Re-read inventory after deposit to reset counters
            inventory, max_items = get_inventory_state(client, char_name)

        # Move to resource tile and gather
        wait_for_cooldown(client, char_name)
        move_character(client, char_name, *tile)

        wait_for_cooldown(client, char_name)
        response = gather(client, char_name)

        if response.status_code == 200:
            inventory_after, _ = get_inventory_state(client, char_name)
            current_after = find_item(inventory_after, item_code)
            gathered = current_after
            logger.info(
                "executor: %s gathered — %s in inv: %d / %d",
                char_name, item_code, current_after, target_qty,
            )
        elif response.status_code == INVENTORY_FULL:
            # Unexpected full — deposit and let the loop continue
            inventory, _ = get_inventory_state(client, char_name)
            logger.info("executor: %s inventory full (497) — depositing", char_name)
            _deposit_all_to_bank(client, char_name, inventory)
        elif response.status_code == 499:
            # Still on cooldown despite wait_for_cooldown — clock skew edge case.
            # Wait again and retry rather than aborting the task.
            logger.warning("executor: %s gather returned 499 (clock skew?) — retrying", char_name)
            wait_for_cooldown(client, char_name)
        else:
            logger.warning("executor: %s gather returned %d — aborting task", char_name, response.status_code)
            break

    else:
        logger.warning(
            "executor: %s hit MAX_ACTIONS=%d for task %s — marking done anyway",
            char_name, MAX_ACTIONS, task_id[:8],
        )

    # Final deposit: anything remaining in inventory goes to bank
    inventory, _ = get_inventory_state(client, char_name)
    total_remaining = sum(s.get("quantity", 0) for s in inventory)
    if total_remaining > 0:
        _deposit_all_to_bank(client, char_name, inventory)


def execute_craft_task(client, char_name: str, task: dict, cache: dict) -> None:
    """
    Craft item_code × quantity:
      1. Withdraw ingredients from bank.
      2. Move to workshop tile.
      3. Craft.
      4. Deposit result to bank.
    """
    item_code = task["item_code"]
    quantity  = task["quantity"]
    meta      = task.get("meta") or {}

    recipe = get_cached_recipe(client, item_code)
    if not recipe:
        raise RuntimeError(f"no recipe for {item_code!r}")

    craft_skill, _ = get_craft_skill(client, item_code)
    workshop_code  = workshop_code_for_skill(craft_skill)
    if not workshop_code:
        raise RuntimeError(f"no workshop code for skill {craft_skill!r}")

    workshop_tiles = find_content(cache, workshop_code)
    if not workshop_tiles:
        raise RuntimeError(f"no workshop tile for {workshop_code!r} in map cache")
    workshop_tile = workshop_tiles[0]["x"], workshop_tiles[0]["y"]

    # --- Move to bank, deposit anything in inventory, then withdraw ---
    # Deposit first to make room — otherwise withdraw may hit 497 (inventory full).
    wait_for_cooldown(client, char_name)
    move_character(client, char_name, *BANK_TILE)
    inventory, _ = get_inventory_state(client, char_name)
    for slot in inventory:
        code = slot.get("code", "")
        qty  = slot.get("quantity", 0)
        if code and qty > 0:
            wait_for_cooldown(client, char_name)
            deposit_item(client, char_name, code, qty)

    for ingredient in recipe:
        mat_code = ingredient["code"]
        mat_qty  = ingredient["quantity"] * quantity
        wait_for_cooldown(client, char_name)
        resp = withdraw_item(client, char_name, mat_code, mat_qty)
        if resp.status_code == 499:
            # Clock skew edge case: wait again and retry once
            wait_for_cooldown(client, char_name)
            resp = withdraw_item(client, char_name, mat_code, mat_qty)
        if resp.status_code != 200:
            raise RuntimeError(f"withdraw {mat_code} × {mat_qty} failed: {resp.status_code}")
        logger.info("executor: %s withdrew %s × %d", char_name, mat_code, mat_qty)

    # --- Move to workshop and craft ---
    wait_for_cooldown(client, char_name)
    move_character(client, char_name, *workshop_tile)
    wait_for_cooldown(client, char_name)
    resp = craft_action(client, char_name, item_code, quantity)
    if resp.status_code == 499:
        wait_for_cooldown(client, char_name)
        resp = craft_action(client, char_name, item_code, quantity)
    if resp.status_code != 200:
        raise RuntimeError(f"craft {item_code} × {quantity} failed: {resp.status_code}")
    logger.info("executor: %s crafted %s × %d", char_name, item_code, quantity)

    # --- Deposit everything to bank ---
    wait_for_cooldown(client, char_name)
    move_character(client, char_name, *BANK_TILE)
    inventory, _ = get_inventory_state(client, char_name)
    for slot in inventory:
        code = slot.get("code", "")
        qty  = slot.get("quantity", 0)
        if code and qty > 0:
            wait_for_cooldown(client, char_name)
            deposit_item(client, char_name, code, qty)
            logger.info("executor: %s deposited %s × %d", char_name, code, qty)


def execute_equip_task(client, char_name: str, task: dict, cache: dict) -> None:
    """
    Equip item_code on char_name:
      source="inventory": equip directly.
      source="bank":      withdraw first, then equip.
    Reads item type from cache to determine the equipment slot.
    """
    item_code = task["item_code"]
    meta      = task.get("meta") or {}
    source    = meta.get("source", "inventory")

    # Re-check: maybe already equipped (e.g. from a previous partial run)
    profile = {slot: "" for slot in EQUIPMENT_SLOTS}
    resp = client.get(f"/characters/{char_name}")
    if resp.status_code == 200:
        char_data = resp.json()["data"]
        profile.update({slot: char_data.get(slot, "") for slot in EQUIPMENT_SLOTS})
    if is_item_equipped(profile, item_code):
        logger.info("executor: %s — %s already equipped, skipping", char_name, item_code)
        return

    if source == "bank":
        wait_for_cooldown(client, char_name)
        move_character(client, char_name, *BANK_TILE)
        wait_for_cooldown(client, char_name)
        resp = withdraw_item(client, char_name, item_code, 1)
        if resp.status_code == 499:
            wait_for_cooldown(client, char_name)
            resp = withdraw_item(client, char_name, item_code, 1)
        if resp.status_code != 200:
            raise RuntimeError(f"withdraw {item_code} failed: {resp.status_code}")
        logger.info("executor: %s withdrew %s from bank", char_name, item_code)
        # Refresh profile after withdraw
        resp = client.get(f"/characters/{char_name}")
        if resp.status_code == 200:
            char_data = resp.json()["data"]
            profile.update({slot: char_data.get(slot, "") for slot in EQUIPMENT_SLOTS})

    # Determine slot from item type (via item cache)
    from services.item_cache import get_item_type
    item_type = get_item_type(client, item_code)
    slot = get_slot_for_item(item_type, profile) if item_type else None
    if not slot:
        raise RuntimeError(f"cannot determine equip slot for {item_code!r} (type={item_type!r})")

    wait_for_cooldown(client, char_name)
    resp = equip_item(client, char_name, item_code, slot)
    if resp.status_code == 200:
        logger.info("executor: %s equipped %s → %s", char_name, item_code, slot)
    elif resp.status_code == 485:
        logger.info("executor: %s — %s already equipped (485)", char_name, item_code)
    else:
        raise RuntimeError(f"equip {item_code} failed: {resp.status_code}")


def execute_fight_task(client, char_name: str, task: dict, cache: dict) -> None:
    """
    Fight monster_code `quantity` times for combat XP (level goal training).
    Pre-fight rest if HP < 30%. Post-fight rest if HP drops low.
    """
    monster_code = task["item_code"]
    count        = task["quantity"]

    monster_tiles = find_content(cache, monster_code)
    if not monster_tiles:
        raise RuntimeError(f"no tile for monster {monster_code!r} in map cache")
    tile = monster_tiles[0]["x"], monster_tiles[0]["y"]

    for i in range(count):
        # Pre-fight rest check
        hp, max_hp = get_hp(client, char_name)
        if max_hp > 0 and hp / max_hp < 0.3:
            logger.info("executor: %s HP %.0f%% — resting before fight", char_name, 100 * hp / max_hp)
            wait_for_cooldown(client, char_name)
            rest(client, char_name)

        wait_for_cooldown(client, char_name)
        move_character(client, char_name, *tile)

        wait_for_cooldown(client, char_name)
        resp = fight(client, char_name)

        if resp.status_code == 200:
            result  = parse_fight_result(resp)
            outcome = "win" if result and is_win(result) else "loss"
            logger.info("executor: %s fight %d/%d — %s", char_name, i + 1, count, outcome)
        elif resp.status_code == 499:
            wait_for_cooldown(client, char_name)
        else:
            logger.warning("executor: %s fight returned %d — stopping", char_name, resp.status_code)
            break

        # Post-fight rest
        hp, max_hp = get_hp(client, char_name)
        if max_hp > 0 and hp / max_hp < 0.3:
            wait_for_cooldown(client, char_name)
            rest(client, char_name)


def execute_task(client, char_name: str, task: dict, world_state: dict) -> None:
    """Dispatch to the right executor based on task type."""
    task_type = task["type"]
    cache     = world_state["cache"]

    if task_type == TaskType.GATHER:
        execute_gather_task(client, char_name, task, cache)
    elif task_type == TaskType.CRAFT:
        execute_craft_task(client, char_name, task, cache)
    elif task_type == TaskType.EQUIP:
        execute_equip_task(client, char_name, task, cache)
    elif task_type == TaskType.FIGHT:
        execute_fight_task(client, char_name, task, cache)
    else:
        raise NotImplementedError(f"task type {task_type!r} not implemented")


# ---------------------------------------------------------------------------
# Observability helpers
# ---------------------------------------------------------------------------

def _log_cycle_summary() -> None:
    """
    Print a one-line summary of every goal and a task-count breakdown to the
    log at the start of each cycle. Lets you see progress at a glance:

        [summary] goals: 2 active, 1 completed, 0 blocked
        [summary]   ACTIVE  collect copper_ore×200  tasks: 2 open, 1 done
        [summary]   ACTIVE  level mining→10/Ognerot  tasks: 0 open, 3 done
        [summary] tasks total: open=2 claimed=0 running=0 done=4 blocked=0 failed=0
    """
    all_goals = get_goals()
    all_tasks = get_tasks()

    # Summarise goal statuses
    from collections import Counter
    goal_counts = Counter(g["status"] for g in all_goals)
    logger.info(
        "[summary] goals: %d active, %d completed, %d blocked, %d failed",
        goal_counts.get(GoalStatus.ACTIVE, 0),
        goal_counts.get(GoalStatus.COMPLETED, 0),
        goal_counts.get(GoalStatus.BLOCKED, 0),
        goal_counts.get(GoalStatus.FAILED, 0),
    )

    # Per-goal line with task breakdown
    tasks_by_goal: dict[str, list[dict]] = {}
    for t in all_tasks:
        tasks_by_goal.setdefault(t["goal_id"], []).append(t)

    for goal in all_goals:
        gtasks = tasks_by_goal.get(goal["id"], [])
        tc = Counter(t["status"] for t in gtasks)

        # Build a short human-readable goal description
        if goal.get("target_item_code") and goal.get("target_quantity"):
            what = f"{goal['target_item_code']}×{goal['target_quantity']}"
        elif goal.get("target_skill") and goal.get("target_level"):
            char = goal.get("target_character", "?")
            what = f"{goal['target_skill']}→{goal['target_level']}/{char}"
        else:
            what = goal.get("target_item_code") or goal.get("target_skill") or "?"

        logger.info(
            "[summary]   %-10s  %-8s  %s  tasks: %d open, %d running, %d done, %d failed",
            goal["status"].upper(),
            goal["type"],
            what,
            tc.get(TaskStatus.OPEN, 0) + tc.get(TaskStatus.CLAIMED, 0),
            tc.get(TaskStatus.RUNNING, 0),
            tc.get(TaskStatus.DONE, 0),
            tc.get(TaskStatus.FAILED, 0),
        )

    # Global task breakdown
    task_counts = Counter(t["status"] for t in all_tasks)
    logger.info(
        "[summary] tasks total: open=%d claimed=%d running=%d done=%d blocked=%d failed=%d",
        task_counts.get(TaskStatus.OPEN, 0),
        task_counts.get(TaskStatus.CLAIMED, 0),
        task_counts.get(TaskStatus.RUNNING, 0),
        task_counts.get(TaskStatus.DONE, 0),
        task_counts.get(TaskStatus.BLOCKED, 0),
        task_counts.get(TaskStatus.FAILED, 0),
    )


# ---------------------------------------------------------------------------
# Main dispatch loop
# ---------------------------------------------------------------------------

def run_goals_loop(client, max_cycles: int | None = None) -> None:
    """
    Main loop: plan → assign → execute → sleep → repeat.

    Each iteration:
      1. run_planning_cycle: evaluates active goals, creates/closes tasks
      2. build_world_state: fresh snapshot for assignment (3 API calls)
      3. for each ready character: find best open task, claim it, execute
      4. sleep until the next character is ready
    """
    cycle_count = 0

    while True:
        logger.info("=== goals loop cycle %d ===", cycle_count + 1)

        # Observability: print a compact status summary before planning so the
        # log shows where things stand at the start of each cycle — useful for
        # debugging stalls and verifying progress without a debugger.
        _log_cycle_summary()

        # Step 1: planning
        run_planning_cycle(client)

        # Check if there's still work to do
        active_goals = get_goals(status=GoalStatus.ACTIVE)
        if not active_goals:
            logger.info("goals: all goals completed or no active goals — stopping")
            break

        # Step 2: fresh world state for assignment scoring
        world_state = build_world_state(client)
        ready = find_ready_characters(world_state["characters"])

        # Step 3: assign and execute
        # Iterate over open tasks and pick the BEST character for each task —
        # not the other way around. This ensures the highest-scored character
        # (e.g. Ognerot for mining) gets the task, not whoever happens to be
        # first in the ready list.
        open_tasks = [t for t in world_state["tasks"] if t["status"] == TaskStatus.OPEN]
        assigned_chars: set[str] = set()
        ready_names = {c["name"] for c in ready}

        for task in open_tasks:
            best_name = find_best_character_for_task(task, world_state)
            if best_name is None or best_name in assigned_chars:
                continue

            # Best character must be ready this cycle (not on cooldown)
            if best_name not in ready_names:
                logger.debug("goals: best char %s for task %s is not ready — skipping",
                             best_name, task["id"][:8])
                continue

            # Atomic claim
            if not claim_task(task["id"], best_name):
                logger.debug("goals: task %s already claimed", task["id"][:8])
                continue

            assigned_chars.add(best_name)

            name = best_name
            logger.info("--- %s → task %s (%s %s × %d) ---",
                        name, task["id"][:8], task["type"],
                        task.get("item_code", ""), task.get("quantity", 0))

            update_task_status(task["id"], TaskStatus.RUNNING)
            try:
                execute_task(client, name, task, world_state)
                update_task_status(task["id"], TaskStatus.DONE)
                release_reservations_for_task(task["id"])
                logger.info("goals: %s task %s DONE", name, task["id"][:8])
            except NotImplementedError:
                update_task_status(task["id"], TaskStatus.BLOCKED, "executor not implemented")
            except Exception as exc:
                logger.error("goals: %s task %s FAILED — %s: %s",
                             name, task["id"][:8], type(exc).__name__, exc)
                update_task_status(task["id"], TaskStatus.FAILED, str(exc))

        cycle_count += 1
        if max_cycles is not None and cycle_count >= max_cycles:
            logger.info("goals: reached max_cycles=%d — stopping", max_cycles)
            break

        # Step 4: sleep until next character is ready
        characters = get_all_characters(client)
        wait = sleep_until_next_ready(characters)
        if wait > 0:
            logger.info("goals: sleeping %.1fs until next character is ready", wait)
            time.sleep(wait)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Artifacts MMO goal runner")
    parser.add_argument(
        "--cycles",
        type=int,
        default=None,
        help="stop after N dispatch iterations (default: run until all goals complete)",
    )
    args = parser.parse_args()

    token = os.getenv("ARTIFACTS_TOKEN")
    if not token:
        logger.error("ARTIFACTS_TOKEN not set in .env")
        sys.exit(1)

    client = ArtifactsClient(token)

    # Initialise DB schema (idempotent)
    init_db()

    # Register goals that aren't already active in the DB
    existing = {
        (g["type"], g["target_item_code"], g["target_quantity"],
         g["target_skill"], g["target_level"], g["target_character"])
        for g in get_goals()
        if g["status"] == GoalStatus.ACTIVE
    }
    for goal in GOALS:
        key = (goal.type, goal.target_item_code, goal.target_quantity,
               goal.target_skill, goal.target_level, goal.target_character)
        if key not in existing:
            insert_goal(goal.to_dict())
            logger.info("goals: registered %s goal — %s",
                        goal.type, goal.target_item_code or goal.target_skill)
        else:
            logger.info("goals: %s goal already active — skipping insert",
                        goal.type)

    logger.info("goals: %d active goal(s)", len(get_goals(status=GoalStatus.ACTIVE)))

    try:
        run_goals_loop(client, max_cycles=args.cycles)
    except KeyboardInterrupt:
        logger.info("goals: stopped by user (Ctrl+C)")


if __name__ == "__main__":
    main()
