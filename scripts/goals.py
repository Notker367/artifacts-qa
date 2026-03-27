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
from services.movement import move_character
from services.gathering import gather
from services.inventory import get_inventory_state, find_item
from services.bank import deposit_item
from services.multi_char import find_ready_characters, get_all_characters, sleep_until_next_ready
from services.map_cache import find_content
from services.item_data import resource_for_item
from services.goal_store import (
    init_db,
    insert_goal,
    get_goals,
    update_task_status,
    release_reservations_for_task,
    claim_task,
)
from services.goals import Goal, GoalStatus, TaskStatus, TaskType
from services.world_state import build_world_state
from services.planner import run_planning_cycle
from services.assignment import find_best_task_for_character
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
    Goal.collect("copper_ore", 200),
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
        else:
            logger.warning("executor: %s gather returned %d", char_name, response.status_code)
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


def execute_task(client, char_name: str, task: dict, world_state: dict) -> None:
    """Dispatch to the right executor based on task type."""
    task_type = task["type"]

    if task_type == TaskType.GATHER:
        execute_gather_task(client, char_name, task, world_state["cache"])
    else:
        logger.warning("executor: task type %r not yet implemented", task_type)
        raise NotImplementedError(f"task type {task_type!r} not implemented")


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
        for char in ready:
            name = char["name"]
            task = find_best_task_for_character(char, world_state)
            if task is None:
                logger.debug("goals: %s — no suitable task this cycle", name)
                continue

            # Atomic claim: prevents two characters taking the same task
            if not claim_task(task["id"], name):
                logger.debug("goals: %s — task %s already claimed", name, task["id"][:8])
                continue

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
