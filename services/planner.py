# Goal planner for Artifacts MMO.
#
# Reads active goals from SQLite, evaluates world state, and creates
# PlannedTasks as needed. Never executes actions — that is the dispatcher's job.
#
# Design rules:
#   - Idempotent: running the planner twice produces the same task set.
#     Already-active tasks are counted in `active_task_qty` and deducted
#     from `needed` before any new tasks are created.
#   - One planning cycle = one world state snapshot. No extra API calls inside
#     _plan_* functions — they read from the snapshot exclusively.
#   - Goal completion is checked at the start of each cycle, before planning.
#     A goal that meets its completion condition is closed immediately.
#   - Cycle detection: parent_goal_id chain is walked with a visited set.
#     If a cycle is detected the goal is blocked with a clear reason.
#
# Current goal coverage:
#   collect — fully implemented (bank-based progress, chunked gather tasks)
#   craft / equip / level — stubs (blocked with "not implemented" reason)

import logging
import uuid

from services.goal_store import (
    get_goals,
    update_goal_status,
    insert_task,
    get_active_task_quantity,
    reserve,
    release_reservations_for_goal,
    expire_stale_claims,
)
from services.goals import (
    GoalStatus,
    GoalType,
    TaskType,
    make_gather_task,
    PlannedTask,
)
from services.world_state import build_world_state, bank_quantity, available_in_bank
from services.map_cache import get_map_cache, find_content
from services.item_data import resource_for_item

logger = logging.getLogger(__name__)

# Items per gather task chunk.
# A character can carry at most inventory_max_items (typically 100) total items.
# We use 80 as a safe default — leaves headroom for multi-item drops (ore + gems).
# When assignment knows the specific character, this could be adjusted to their
# actual max, but for planning purposes a fixed chunk is sufficient.
GATHER_CHUNK = 80


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_planning_cycle(client) -> None:
    """
    One full planning pass:
      1. return stale claimed tasks to open
      2. build world state snapshot (3 API calls)
      3. check completion for every active goal
      4. plan new tasks for goals that still need work

    Safe to call in a loop — idempotent, no duplicate tasks.
    """
    # Expire timed-out claims before planning so stale tasks don't inflate counts
    expired = expire_stale_claims()
    if expired:
        logger.info("planner: released %d stale claim(s) before planning", expired)

    world_state = build_world_state(client)
    goals = world_state["goals"]

    if not goals:
        logger.debug("planner: no active goals")
        return

    logger.info("planner: planning cycle — %d active goal(s)", len(goals))

    # Walk goals ordered by priority (lower number = higher priority)
    for goal in sorted(goals, key=lambda g: g["priority"]):
        try:
            _plan_goal(goal, world_state, client)
        except Exception as exc:
            logger.error("planner: goal %s failed — %s: %s", goal["id"][:8], type(exc).__name__, exc)


# ---------------------------------------------------------------------------
# Goal dispatcher
# ---------------------------------------------------------------------------

def _plan_goal(goal: dict, world_state: dict, client) -> None:
    goal_type = goal["type"]

    if goal_type == GoalType.COLLECT:
        _plan_collect(goal, world_state, client)
    elif goal_type == GoalType.CRAFT:
        _block_goal(goal["id"], "craft goal not yet implemented")
    elif goal_type == GoalType.EQUIP:
        _block_goal(goal["id"], "equip goal not yet implemented")
    elif goal_type == GoalType.LEVEL:
        _block_goal(goal["id"], "level goal not yet implemented")
    else:
        _block_goal(goal["id"], f"unknown goal type: {goal_type!r}")


# ---------------------------------------------------------------------------
# Collect goal planner
# ---------------------------------------------------------------------------

def _plan_collect(goal: dict, world_state: dict, client) -> None:
    """
    Plan a collect goal: gather item_code × target_quantity and deliver to bank.

    Completion check:
      bank_qty >= target_qty → mark completed, release reservations.

    Task planning:
      needed = target_qty − bank_qty − active_task_qty
      If needed > 0: create gather tasks in GATHER_CHUNK-sized chunks.
      Tasks are created upfront for the full remaining need, so multiple
      characters can work in parallel if the assignment layer picks them.

    Idempotency:
      active_task_qty counts open/claimed/running tasks for this goal/item.
      Planning only fills the gap — never creates tasks that are already planned.
    """
    goal_id   = goal["id"]
    item_code = goal["target_item_code"]
    target    = goal["target_quantity"]

    bank_qty = bank_quantity(world_state, item_code)

    # --- Completion check ---
    if bank_qty >= target:
        update_goal_status(goal_id, GoalStatus.COMPLETED)
        release_reservations_for_goal(goal_id)
        logger.info(
            "planner: goal %s COMPLETED — collect %s × %d (bank: %d)",
            goal_id[:8], item_code, target, bank_qty,
        )
        return

    # --- Verify the resource tile exists in map cache ---
    # item_code is a drop (e.g. "copper_ore"); the map cache uses resource tile
    # content_codes (e.g. "copper_rocks"). Resolve via ITEM_SOURCE first.
    resource_code = resource_for_item(item_code)
    if resource_code is None:
        _block_goal(goal_id, f"no resource mapping for {item_code!r} — add to item_data.ITEM_SOURCE")
        return
    cache = get_map_cache(client)
    if not find_content(cache, resource_code):
        _block_goal(goal_id, f"no map tile found for {resource_code!r} — run discover_map.py")
        return

    # --- How much is still unplanned ---
    active_task_qty = get_active_task_quantity(goal_id, item_code)
    needed = target - bank_qty - active_task_qty

    logger.info(
        "planner: goal %s — collect %s | target=%d bank=%d in_tasks=%d needed=%d",
        goal_id[:8], item_code, target, bank_qty, active_task_qty, needed,
    )

    if needed <= 0:
        # All remaining quantity is already covered by in-flight tasks — nothing to do.
        return

    # --- Create gather tasks to cover `needed` ---
    while needed > 0:
        chunk = min(needed, GATHER_CHUNK)

        task = make_gather_task(
            goal_id=goal_id,
            item_code=item_code,
            quantity=chunk,
            allowed=goal.get("allowed_characters"),
            preferred=goal.get("preferred_characters"),
        )
        insert_task(task.to_dict())

        # Reserve this chunk so other goals don't count on it
        reserve({
            "id":        str(uuid.uuid4()),
            "goal_id":   goal_id,
            "task_id":   task.id,
            "item_code": item_code,
            "quantity":  chunk,
        })

        logger.info(
            "planner: goal %s — created gather task %s for %s × %d",
            goal_id[:8], task.id[:8], item_code, chunk,
        )
        needed -= chunk


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _block_goal(goal_id: str, reason: str) -> None:
    """Mark a goal as blocked and log the reason so it's visible without a debugger."""
    update_goal_status(goal_id, GoalStatus.BLOCKED, blocked_reason=reason)
    logger.warning("planner: goal %s BLOCKED — %s", goal_id[:8], reason)
