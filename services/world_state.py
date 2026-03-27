# World state snapshot for the goal planner.
#
# Builds a single consistent view of everything the planner needs to make
# decisions in one planning cycle. All API calls happen here — planner.py
# reads from the snapshot without touching the network.
#
# What's included:
#   characters   — list of raw character dicts (same structure as GET /my/characters)
#   bank         — {item_code: quantity} for quick bank lookup
#   goals        — all active Goal dicts from SQLite
#   tasks        — all non-terminal Task dicts from SQLite (open/claimed/running)
#   reservations — {item_code: total_reserved_qty} across all active goals
#
# Why one snapshot per cycle:
#   Bank state and character cooldowns change while the planner is running.
#   Reading them once at the start of the cycle keeps decisions consistent
#   and avoids N extra API calls inside the planning logic.

import logging

from services.bank import get_bank_items
from services.multi_char import get_all_characters
from services.map_cache import get_map_cache
from services.goal_store import get_goals, get_tasks, get_all_reserved_quantities
from services.goals import GoalStatus, TaskStatus

logger = logging.getLogger(__name__)


def build_world_state(client) -> dict:
    """
    Fetch all inputs the planner and assignment scorer need, return a single snapshot.

    API calls made:
      - GET /my/characters
      - GET /my/bank/items
      - map cache (file read; API only if cache is stale)

    SQLite reads for goals/tasks/reservations are cheap local queries.
    The cache is included so the assignment scorer can check tile proximity
    without an extra API call per character.
    """
    logger.debug("world_state: fetching characters, bank and map cache")
    characters = get_all_characters(client)
    bank_items = get_bank_items(client)
    cache = get_map_cache(client)

    # Convert bank list to a lookup dict — planner checks quantities by code constantly.
    bank = {item["code"]: item["quantity"] for item in bank_items if item.get("code")}

    # Active goals and all in-flight tasks from SQLite
    goals = get_goals(status=GoalStatus.ACTIVE)
    tasks = get_tasks(status=TaskStatus.OPEN) + \
            get_tasks(status=TaskStatus.CLAIMED) + \
            get_tasks(status=TaskStatus.RUNNING)

    # Reservations as a lookup dict — planner subtracts this from available quantities
    reservations = get_all_reserved_quantities()

    logger.debug(
        "world_state: %d characters | bank: %d item types | %d active goals | %d in-flight tasks",
        len(characters), len(bank), len(goals), len(tasks),
    )

    return {
        "characters":   characters,
        "bank":         bank,
        "cache":        cache,
        "goals":        goals,
        "tasks":        tasks,
        "reservations": reservations,
    }


# ---------------------------------------------------------------------------
# Convenience accessors used by planner
# ---------------------------------------------------------------------------

def bank_quantity(world_state: dict, item_code: str) -> int:
    """Return how many of item_code are currently in the bank."""
    return world_state["bank"].get(item_code, 0)


def reserved_quantity(world_state: dict, item_code: str) -> int:
    """Return how many of item_code are reserved across all active goals."""
    return world_state["reservations"].get(item_code, 0)


def available_in_bank(world_state: dict, item_code: str) -> int:
    """
    Return bank quantity minus reservations for item_code.
    This is the amount the planner can freely allocate to new tasks without
    conflicting with resources already spoken for by other goals.
    """
    return max(0, bank_quantity(world_state, item_code) - reserved_quantity(world_state, item_code))


def character_by_name(world_state: dict, name: str) -> dict | None:
    """Return the character dict for the given name, or None if not found."""
    for char in world_state["characters"]:
        if char.get("name") == name:
            return char
    return None
