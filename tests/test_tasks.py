# Task tests for Artifacts MMO.
# Tasks are objectives from Taskmaster NPCs — kill monsters or deliver items.
# Reward: gold + task coins on completion.
#
# Taskmaster tiles:
#   (1, 2)  — City, monsters tasks
#   (4, 13) — Forest, items tasks
#
# Test structure:
#   - state reads: fast, no cooldown needed
#   - accept flow: stateful, needs taskmaster tile
#   - complete flow: @pytest.mark.long (requires actually finishing the objective)

import logging
import pytest

from services.cooldown import wait_for_cooldown
from services.movement import move_character
from services.tasks import (
    get_task_state,
    has_active_task,
    is_task_complete,
    accept_task,
    complete_task,
    cancel_task,
    parse_task_reward,
    parse_accepted_task,
)
from services.errors import NO_TASK, TASK_NOT_COMPLETE

logger = logging.getLogger(__name__)

# Taskmaster for monster tasks — closest to starting area
MONSTERS_TASKMASTER_TILE = (1, 2)


# --- State read tests (no cooldown, no actions) ---

def test_get_task_state_has_required_fields(client, character_name):
    """
    Task state must include all four fields: task, task_type, task_progress, task_total.
    These are the minimum needed to drive task-aware scenario decisions.
    """
    state = get_task_state(client, character_name)

    for field in ("task", "task_type", "task_progress", "task_total"):
        assert field in state, f"task state missing field: {field!r}"

    assert isinstance(state["task"], str), "task must be a string"
    assert isinstance(state["task_progress"], int), "task_progress must be int"
    assert isinstance(state["task_total"], int), "task_total must be int"

    logger.info(
        "task state: task=%r type=%r progress=%d/%d",
        state["task"],
        state["task_type"],
        state["task_progress"],
        state["task_total"],
    )


def test_task_helper_logic():
    """
    has_active_task and is_task_complete must work correctly on plain dicts — no API needed.
    """
    no_task = {"task": "", "task_type": "", "task_progress": 0, "task_total": 0}
    active_incomplete = {"task": "chicken", "task_type": "monsters", "task_progress": 3, "task_total": 10}
    active_complete = {"task": "chicken", "task_type": "monsters", "task_progress": 10, "task_total": 10}

    assert not has_active_task(no_task), "empty task field = no active task"
    assert has_active_task(active_incomplete), "non-empty task field = active task"
    assert has_active_task(active_complete), "completed task is still active until turned in"

    assert not is_task_complete(no_task), "no task = not complete"
    assert not is_task_complete(active_incomplete), "progress < total = not complete"
    assert is_task_complete(active_complete), "progress == total = complete"

    logger.info("task helper logic: all checks passed")


# --- Stateful tests ---

def test_accept_task_at_taskmaster(client, character_name):
    """
    Moving to the Taskmaster tile and calling task/new must assign a task.
    Skips if character already has an active task — cancelling costs a task coin,
    so we don't cancel just for test isolation.
    """
    state = get_task_state(client, character_name)
    if has_active_task(state):
        logger.info("character already has task %r — verifying state is valid and skipping accept", state["task"])
        assert state["task_total"] > 0, "existing task must have total > 0"
        pytest.skip(f"character already has task {state['task']!r} — accept step not needed")

    # Move to taskmaster and accept new task
    wait_for_cooldown(client, character_name)
    move_character(client, character_name, *MONSTERS_TASKMASTER_TILE)

    wait_for_cooldown(client, character_name)
    response = accept_task(client, character_name)

    assert response.status_code == 200, (
        f"expected 200 from task/new, got {response.status_code}: {response.text}"
    )

    accepted = parse_accepted_task(response)
    assert accepted is not None, "task/new response must contain task data"
    assert accepted.get("code"), "accepted task must have a non-empty code"
    assert accepted.get("total", 0) > 0, "accepted task must have total > 0"

    # Verify task is now visible on character state
    state_after = get_task_state(client, character_name)
    assert has_active_task(state_after), "character must have active task after accept"
    assert state_after["task"] == accepted["code"], (
        f"character task code mismatch: {state_after['task']!r} vs {accepted['code']!r}"
    )

    logger.info(
        "task accepted: %s (type=%s, total=%d)",
        accepted["code"],
        accepted.get("type"),
        accepted["total"],
    )


def test_complete_task_without_progress_returns_488(client, character_name):
    """
    Attempting to complete a task before meeting the objective must return 488.
    487 = no task at all; 488 = task active but objective not met.
    This validates the negative path — task completion is gated by actual progress.
    Character must have an active task (accepted in previous test or pre-existing).
    """
    state = get_task_state(client, character_name)
    if not has_active_task(state):
        pytest.skip("no active task — run test_accept_task_at_taskmaster first")

    if is_task_complete(state):
        pytest.skip("task already complete — this test targets incomplete tasks")

    # Try to complete at taskmaster tile (wrong state, correct location)
    wait_for_cooldown(client, character_name)
    move_character(client, character_name, *MONSTERS_TASKMASTER_TILE)

    wait_for_cooldown(client, character_name)
    response = complete_task(client, character_name)

    assert response.status_code == TASK_NOT_COMPLETE, (
        f"expected 488 (task not complete), got {response.status_code}: {response.text}"
    )
    logger.info(
        "complete blocked correctly (488): task=%r progress=%d/%d",
        state["task"],
        state["task_progress"],
        state["task_total"],
    )


@pytest.mark.long
def test_complete_task_end_to_end(client, character_name):
    """
    Full task flow: accept → fight until objective met → complete → verify reward.
    Uses chicken (0, 1) for a monster task. May take many fight cycles.
    Only runs with pytest -m long.
    """
    from services.combat import fight, parse_fight_result, is_win
    from services.rest import get_hp, is_full_hp, rest

    MONSTER_TILE = (0, 1)
    HP_THRESHOLD = 0.4  # rest when below 40%

    # Ensure we have an active monster task
    wait_for_cooldown(client, character_name)
    state = get_task_state(client, character_name)

    if not has_active_task(state) or state["task_type"] != "monsters":
        # Accept a monsters task
        move_character(client, character_name, *MONSTERS_TASKMASTER_TILE)
        wait_for_cooldown(client, character_name)
        resp = accept_task(client, character_name)
        assert resp.status_code == 200, f"failed to accept task: {resp.text}"
        state = get_task_state(client, character_name)

    logger.info("starting task: %s %d/%d", state["task"], state["task_progress"], state["task_total"])

    # Fight until task objective is met
    wait_for_cooldown(client, character_name)
    move_character(client, character_name, *MONSTER_TILE)

    while not is_task_complete(get_task_state(client, character_name)):
        wait_for_cooldown(client, character_name)

        # Rest if HP is low before engaging
        hp, max_hp = get_hp(client, character_name)
        if hp / max_hp < HP_THRESHOLD:
            logger.info("HP low (%.0f%%), resting", 100 * hp / max_hp)
            rest(client, character_name)
            wait_for_cooldown(client, character_name)

        response = fight(client, character_name)
        assert response.status_code == 200, f"fight failed: {response.text}"

        result = parse_fight_result(response)
        current = get_task_state(client, character_name)
        logger.info(
            "fight %s — task progress: %d/%d",
            "win" if result and is_win(result) else "loss",
            current["task_progress"],
            current["task_total"],
        )

    # Complete the task at the taskmaster
    wait_for_cooldown(client, character_name)
    move_character(client, character_name, *MONSTERS_TASKMASTER_TILE)

    wait_for_cooldown(client, character_name)
    response = complete_task(client, character_name)
    assert response.status_code == 200, (
        f"expected 200 from task/complete, got {response.status_code}: {response.text}"
    )

    reward = parse_task_reward(response)
    assert reward is not None, "task complete response must contain rewards"
    assert reward.get("gold", 0) >= 0, "reward gold must be non-negative"

    logger.info(
        "task complete: gold=%d task_coin=%s items=%s",
        reward.get("gold", 0),
        reward.get("task_coin"),
        reward.get("items", []),
    )
