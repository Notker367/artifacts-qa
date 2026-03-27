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
    insert_goal,
    update_goal_status,
    insert_task,
    get_active_task_quantity,
    task_exists,
    sub_goal_exists,
    get_sub_goal_blocked_reason,
    count_failed_tasks,
    reserve,
    release_reservations_for_goal,
    expire_stale_claims,
)
from services.goals import (
    Goal,
    GoalStatus,
    GoalType,
    TaskType,
    make_gather_task,
    make_craft_task,
    make_equip_task,
    make_fight_task,
)
from services.world_state import (
    build_world_state,
    bank_quantity,
    available_in_bank,
    character_by_name,
)
from services.map_cache import get_map_cache, find_content, find_tiles
from services.item_data import (
    resource_for_item,
    workshop_code_for_skill,
    train_resource_for_skill,
    drop_for_resource,
)
from services.item_cache import get_cached_recipe, get_craft_skill, get_cached_item
from services.inventory import find_item
from services.equipment import is_item_equipped

logger = logging.getLogger(__name__)

# Items per gather task chunk.
# A character can carry at most inventory_max_items (typically 100) total items.
# The early-deposit threshold is 80% = 80 items. With multi-item drops (ore + gem
# + craft result), the target item count in inventory can be 5-10 lower than total.
# 60 leaves enough headroom so the task completes before the 80-item threshold fires.
GATHER_CHUNK = 60


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

# Max consecutive task failures before the goal is blocked.
# Prevents infinite retry storms when a task fails repeatedly (e.g. 497 loop).
MAX_TASK_FAILURES = 5


def _plan_goal(goal: dict, world_state: dict, client) -> None:
    goal_type = goal["type"]
    goal_id   = goal["id"]

    # Block the goal if too many tasks have already failed — avoids tight retry loops
    # where a task fails immediately and the planner queues a new one every cycle.
    failures = count_failed_tasks(goal_id)
    if failures >= MAX_TASK_FAILURES:
        _block_goal(goal_id, f"too many task failures ({failures}) — investigate and reset DB")
        return

    if goal_type == GoalType.COLLECT:
        _plan_collect(goal, world_state, client)
    elif goal_type == GoalType.CRAFT:
        _plan_craft(goal, world_state, client)
    elif goal_type == GoalType.EQUIP:
        _plan_equip(goal, world_state, client)
    elif goal_type == GoalType.LEVEL:
        _plan_level(goal, world_state, client)
    else:
        _block_goal(goal_id, f"unknown goal type: {goal_type!r}")


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
# Craft goal planner
# ---------------------------------------------------------------------------

# How many craft actions to put in one task.
# Craft actions are fast (~4s cooldown) so a larger batch per task is fine.
CRAFT_BATCH = 10


def _plan_craft(goal: dict, world_state: dict, client) -> None:
    """
    Plan a craft goal: craft item_code × target_quantity.

    Completion: bank_qty >= target_quantity.

    Flow:
      1. Check recipe (block if none).
      2. Check workshop tile exists in map cache (block if missing).
      3. For each missing ingredient: spawn collect sub-goal if not already active.
      4. If all materials available in bank (minus reservations): create craft task.
    """
    goal_id   = goal["id"]
    item_code = goal["target_item_code"]
    target    = goal["target_quantity"]

    bank_qty = bank_quantity(world_state, item_code)
    if bank_qty >= target:
        update_goal_status(goal_id, GoalStatus.COMPLETED)
        release_reservations_for_goal(goal_id)
        logger.info("planner: goal %s COMPLETED — craft %s × %d (bank: %d)",
                    goal_id[:8], item_code, target, bank_qty)
        return

    recipe = get_cached_recipe(client, item_code)
    if not recipe:
        _block_goal(goal_id, f"no recipe found for {item_code!r}")
        return

    craft_skill, required_level = get_craft_skill(client, item_code)
    if not craft_skill:
        _block_goal(goal_id, f"could not determine craft skill for {item_code!r}")
        return

    workshop_code = workshop_code_for_skill(craft_skill)
    if not workshop_code:
        _block_goal(goal_id, f"no workshop code mapping for skill {craft_skill!r}")
        return
    cache = get_map_cache(client)
    if not find_content(cache, workshop_code):
        _block_goal(goal_id,
                    f"no workshop tile for {craft_skill!r} (code={workshop_code!r}) "
                    f"— run discover_map.py to verify content_codes")
        return

    # How many crafts are still needed (account for in-flight craft tasks)
    active_craft_qty = get_active_task_quantity(goal_id, item_code)
    needed_crafts = target - bank_qty - active_craft_qty
    if needed_crafts <= 0:
        return

    # Check materials and spawn sub-goals for any shortfalls.
    # An ingredient can itself be craftable (e.g. copper_ore → copper_bar → copper_dagger).
    # Check the item cache: if the ingredient has a recipe, spawn a CRAFT sub-goal;
    # otherwise spawn a COLLECT (gather) sub-goal.
    all_available = True
    for ingredient in recipe:
        mat_code   = ingredient["code"]
        mat_needed = ingredient["quantity"] * needed_crafts
        avail      = available_in_bank(world_state, mat_code)

        if avail < mat_needed:
            all_available = False
            missing = mat_needed - avail

            # If a blocked sub-goal already exists for this ingredient, the parent
            # cannot proceed either — propagate the block rather than looping forever.
            blocked_reason = get_sub_goal_blocked_reason(goal_id, mat_code)
            if blocked_reason:
                _block_goal(goal_id, f"sub-goal for {mat_code!r} is blocked: {blocked_reason}")
                return

            # Decide sub-goal type based on whether the ingredient has a recipe.
            #
            # Sub-goal target = mat_needed (total required), NOT missing (current gap).
            # If target were set to `missing`, the sub-goal would complete immediately
            # when bank_qty >= missing — even if the total need (mat_needed) isn't met
            # yet. Using mat_needed ensures the sub-goal only completes when the full
            # quantity needed by the parent craft is present in the bank.
            mat_recipe = get_cached_recipe(client, mat_code)
            if mat_recipe:
                # Ingredient is itself craftable — spawn a craft sub-goal
                if not sub_goal_exists(goal_id, GoalType.CRAFT, mat_code):
                    sub = Goal.craft(mat_code, mat_needed,
                                     parent_goal_id=goal_id,
                                     allowed_characters=goal.get("allowed_characters"))
                    insert_goal(sub.to_dict())
                    logger.info("planner: goal %s — spawned craft sub-goal for %s × %d",
                                goal_id[:8], mat_code, mat_needed)
            else:
                # Ingredient is gathered — spawn a collect sub-goal
                if not sub_goal_exists(goal_id, GoalType.COLLECT, mat_code):
                    sub = Goal.collect(mat_code, mat_needed,
                                       parent_goal_id=goal_id,
                                       allowed_characters=goal.get("allowed_characters"))
                    insert_goal(sub.to_dict())
                    logger.info("planner: goal %s — spawned collect sub-goal for %s × %d",
                                goal_id[:8], mat_code, mat_needed)

    if not all_available:
        logger.info("planner: goal %s — craft %s waiting for materials",
                    goal_id[:8], item_code)
        return

    # Materials ready — create craft task in batches
    while needed_crafts > 0:
        batch = min(needed_crafts, CRAFT_BATCH)
        task = make_craft_task(
            goal_id=goal_id,
            item_code=item_code,
            quantity=batch,
            allowed=goal.get("allowed_characters"),
        )
        task.meta = {"craft_skill": craft_skill, "required_level": required_level}
        insert_task(task.to_dict())
        logger.info("planner: goal %s — created craft task %s for %s × %d",
                    goal_id[:8], task.id[:8], item_code, batch)
        needed_crafts -= batch


# ---------------------------------------------------------------------------
# Equip goal planner
# ---------------------------------------------------------------------------

def _plan_equip(goal: dict, world_state: dict, client) -> None:
    """
    Plan an equip goal: equip item_code on target_character.

    Completion: item is already equipped on target_character.

    Flow:
      1. Already equipped → complete.
      2. In character's inventory → create equip task.
      3. In bank (available) → create equip task (executor will withdraw first).
      4. Not found → spawn craft or collect sub-goal.
    """
    goal_id        = goal["id"]
    item_code      = goal["target_item_code"]
    target_char    = goal["target_character"]

    if not target_char:
        _block_goal(goal_id, "equip goal requires target_character")
        return

    char = character_by_name(world_state, target_char)
    if char is None:
        _block_goal(goal_id, f"character {target_char!r} not found in world state")
        return

    # Already equipped — done
    if is_item_equipped(char, item_code):
        update_goal_status(goal_id, GoalStatus.COMPLETED)
        logger.info("planner: goal %s COMPLETED — %s already equipped on %s",
                    goal_id[:8], item_code, target_char)
        return

    # Don't create duplicate tasks
    if task_exists(goal_id, TaskType.EQUIP, item_code):
        return

    # Item in character's inventory → equip directly
    if find_item(char.get("inventory", []), item_code) > 0:
        task = make_equip_task(goal_id, item_code, target_char)
        task.meta = {"source": "inventory"}
        insert_task(task.to_dict())
        logger.info("planner: goal %s — equip task (from inventory) for %s on %s",
                    goal_id[:8], item_code, target_char)
        return

    # Item available in bank → equip task (executor withdraws first)
    if available_in_bank(world_state, item_code) > 0:
        task = make_equip_task(goal_id, item_code, target_char)
        task.meta = {"source": "bank"}
        insert_task(task.to_dict())
        logger.info("planner: goal %s — equip task (from bank) for %s on %s",
                    goal_id[:8], item_code, target_char)
        return

    # Not found anywhere — spawn a sub-goal to obtain the item
    recipe = get_cached_recipe(client, item_code)
    if recipe:
        if not sub_goal_exists(goal_id, GoalType.CRAFT, item_code):
            sub = Goal.craft(item_code, 1, parent_goal_id=goal_id)
            insert_goal(sub.to_dict())
            logger.info("planner: goal %s — spawned craft sub-goal for %s",
                        goal_id[:8], item_code)
    else:
        if not sub_goal_exists(goal_id, GoalType.COLLECT, item_code):
            sub = Goal.collect(item_code, 1, parent_goal_id=goal_id)
            insert_goal(sub.to_dict())
            logger.info("planner: goal %s — spawned collect sub-goal for %s",
                        goal_id[:8], item_code)


# ---------------------------------------------------------------------------
# Level goal planner
# ---------------------------------------------------------------------------

# Fights per task for combat training. Small enough to re-check level often.
FIGHTS_PER_TASK = 10


def _plan_level(goal: dict, world_state: dict, client) -> None:
    """
    Plan a level goal: raise target_skill to target_level on target_character.

    Completion: char's skill level >= target_level.

    Approach:
      - Gathering skills: create gather tasks using SKILL_TRAIN_RESOURCE.
        One gather task at a time (task_exists guard) — planner re-evaluates
        after each task completes and creates another if goal not yet done.
      - Combat: create fight tasks of FIGHTS_PER_TASK each.
      - Crafting skills (weaponcrafting, etc.): not yet supported — blocked.
    """
    goal_id      = goal["id"]
    target_skill = goal["target_skill"]
    target_level = goal["target_level"]
    target_char  = goal["target_character"]

    if not target_char:
        _block_goal(goal_id, "level goal requires target_character")
        return

    char = character_by_name(world_state, target_char)
    if char is None:
        _block_goal(goal_id, f"character {target_char!r} not found in world state")
        return

    # Combat level uses the character's general `level` field
    if target_skill == "combat":
        current = char.get("level", 0)
    else:
        current = char.get(f"{target_skill}_level", 0)

    if current >= target_level:
        update_goal_status(goal_id, GoalStatus.COMPLETED)
        logger.info("planner: goal %s COMPLETED — %s level %d on %s (target %d)",
                    goal_id[:8], target_skill, current, target_char, target_level)
        return

    logger.info("planner: goal %s — level %s | current=%d target=%d on %s",
                goal_id[:8], target_skill, current, target_level, target_char)

    resource_code = train_resource_for_skill(target_skill)
    if resource_code is None:
        _block_goal(goal_id,
                    f"no training resource for skill {target_skill!r} — "
                    f"crafting skills must be levelled by crafting (not yet supported)")
        return

    cache = get_map_cache(client)
    if not find_content(cache, resource_code):
        _block_goal(goal_id,
                    f"no map tile for training resource {resource_code!r} "
                    f"— run discover_map.py")
        return

    allowed = [target_char]  # level goal is always character-specific

    if target_skill == "combat":
        if not task_exists(goal_id, TaskType.FIGHT, resource_code):
            task = make_fight_task(goal_id, resource_code, FIGHTS_PER_TASK,
                                   allowed=allowed)
            insert_task(task.to_dict())
            logger.info("planner: goal %s — created fight task × %d vs %s for %s",
                        goal_id[:8], FIGHTS_PER_TASK, resource_code, target_char)
    else:
        item_code = drop_for_resource(resource_code)
        if item_code is None:
            _block_goal(goal_id, f"no drop mapping for resource {resource_code!r}")
            return
        if not task_exists(goal_id, TaskType.GATHER, item_code):
            task = make_gather_task(goal_id, item_code, GATHER_CHUNK,
                                    allowed=allowed)
            insert_task(task.to_dict())
            logger.info("planner: goal %s — created gather task %s × %d for %s",
                        goal_id[:8], item_code, GATHER_CHUNK, target_char)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _block_goal(goal_id: str, reason: str) -> None:
    """Mark a goal as blocked and log the reason so it's visible without a debugger."""
    update_goal_status(goal_id, GoalStatus.BLOCKED, blocked_reason=reason)
    logger.warning("planner: goal %s BLOCKED — %s", goal_id[:8], reason)
