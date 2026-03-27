# Character assignment and suitability scoring for the goal system.
#
# Assignment is separate from planning and separate from execution:
#   planner.py   — creates open tasks based on goals
#   assignment.py — picks the best character for each open task
#   dispatcher   — claims the task and executes it
#
# Scoring model:
#   Each (character, task) pair gets an integer score.
#   Higher score = better fit. Score 0 = ineligible (never assign).
#
#   Eligibility gates (return 0 immediately if any fails):
#     - character on cooldown (busy, skip this cycle)
#     - hard_assignment: only task.character_name may take it
#     - allowed_characters: character not in the whitelist
#
#   Score bonuses:
#     +30  character is the assigned_character
#     +20  character is in preferred_characters
#     +2×L character's skill level L for the task type (higher skill = faster/safer)
#     +15  character is already at the resource tile (no movement needed)
#
# Two directions are supported:
#   find_best_character_for_task(task, world_state) — given a task, pick a character
#   find_best_task_for_character(char, world_state) — given a character, pick a task
#
# The dispatcher loop uses find_best_task_for_character so each ready character
# can grab work independently without central coordination.

import logging

from services.goals import TaskType, TaskStatus
from services.item_data import resource_for_item, skill_for_resource
from services.map_cache import find_content
from services.multi_char import seconds_until_ready

logger = logging.getLogger(__name__)

# Score bonuses
_BONUS_ASSIGNED   = 30
_BONUS_PREFERRED  = 20
_BONUS_SKILL_MULT = 2   # per skill level point
_BONUS_AT_TILE    = 15


# ---------------------------------------------------------------------------
# Suitability score
# ---------------------------------------------------------------------------

def score_character_for_task(char: dict, task: dict, world_state: dict) -> int:
    """
    Return a suitability score for assigning char to task.
    Returns 0 if the character is ineligible — never assign a 0-scored character.

    Reads character state directly from the world_state snapshot so scoring
    doesn't trigger any API calls.
    """
    name = char.get("name", "")

    # --- Eligibility gates ---

    # Characters on cooldown are busy; skip until the next planning cycle.
    if seconds_until_ready(char) > 0:
        return 0

    # Hard assignment: only one specific character may take this task.
    if task.get("hard_assignment"):
        if task.get("character_name") != name:
            return 0

    # Allowed characters whitelist: None means anyone is allowed.
    allowed = task.get("allowed_characters")
    if allowed and name not in allowed:
        return 0

    # --- Base score ---
    score = 10

    # --- Eligibility bonuses ---
    if task.get("character_name") == name:
        score += _BONUS_ASSIGNED

    preferred = task.get("preferred_characters")
    if preferred and name in preferred:
        score += _BONUS_PREFERRED

    task_type = task.get("type")

    # --- Skill level bonus for gather tasks ---
    if task_type == TaskType.GATHER:
        item_code = task.get("item_code")
        resource_code = resource_for_item(item_code) if item_code else None
        if resource_code:
            skill = skill_for_resource(resource_code)
            if skill:
                level = char.get(f"{skill}_level", 0)
                score += level * _BONUS_SKILL_MULT

            # --- Proximity bonus: already standing on the resource tile ---
            cache = world_state.get("cache")
            if cache:
                tiles = find_content(cache, resource_code)
                if tiles:
                    char_x, char_y = char.get("x"), char.get("y")
                    for tile in tiles:
                        if tile.get("x") == char_x and tile.get("y") == char_y:
                            score += _BONUS_AT_TILE
                            break

    # --- Combat level bonus for fight tasks ---
    # In Artifacts MMO, combat level is the character's general `level` field.
    elif task_type == TaskType.FIGHT:
        combat_level = char.get("level", 0)
        score += combat_level * _BONUS_SKILL_MULT

    # --- Craft skill bonus for craft tasks ---
    # Craft tasks store the target item_code; skill is read from the item cache
    # if available in world_state meta. Fallback: no skill bonus (base score only).
    elif task_type == TaskType.CRAFT:
        meta = task.get("meta") or {}
        craft_skill = meta.get("craft_skill")
        if craft_skill:
            level = char.get(f"{craft_skill}_level", 0)
            score += level * _BONUS_SKILL_MULT

    return score


# ---------------------------------------------------------------------------
# Assignment helpers
# ---------------------------------------------------------------------------

def find_best_character_for_task(task: dict, world_state: dict) -> str | None:
    """
    Return the name of the best eligible character for this task, or None.
    Characters with score 0 (ineligible or on cooldown) are excluded.
    Logs the scoring decision so it's visible without a debugger.
    """
    characters = world_state.get("characters", [])
    scores = {
        char["name"]: score_character_for_task(char, task, world_state)
        for char in characters
        if char.get("name")
    }
    eligible = {name: s for name, s in scores.items() if s > 0}

    if not eligible:
        logger.debug(
            "assignment: task %s (%s %s) — no eligible character (scores: %s)",
            task["id"][:8], task["type"], task.get("item_code", ""), scores,
        )
        return None

    best = max(eligible, key=lambda n: eligible[n])
    logger.info(
        "assignment: task %s (%s %s × %d) → %s (score %d | all: %s)",
        task["id"][:8], task["type"], task.get("item_code", ""), task.get("quantity", 0),
        best, eligible[best],
        {n: s for n, s in sorted(eligible.items(), key=lambda x: -x[1])},
    )
    return best


def find_best_task_for_character(char: dict, world_state: dict) -> dict | None:
    """
    Return the open task that best fits this character, or None.
    Used by the dispatcher loop: each ready character calls this to find work.

    Tasks are scored with the character fixed; highest score wins.
    Only open tasks are considered — claimed/running tasks already have owners.
    """
    open_tasks = [t for t in world_state.get("tasks", []) if t["status"] == TaskStatus.OPEN]
    if not open_tasks:
        return None

    scored = []
    for task in open_tasks:
        s = score_character_for_task(char, task, world_state)
        if s > 0:
            scored.append((s, task))

    if not scored:
        return None

    scored.sort(key=lambda x: -x[0])
    best_score, best_task = scored[0]

    logger.info(
        "assignment: %s → task %s (%s %s × %d) score=%d",
        char["name"], best_task["id"][:8],
        best_task["type"], best_task.get("item_code", ""),
        best_task.get("quantity", 0), best_score,
    )
    return best_task
