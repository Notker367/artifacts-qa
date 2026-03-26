# Task helpers for Artifacts MMO.
# Tasks are objectives assigned by a Taskmaster NPC — kill monsters or deliver items.
# Completing tasks rewards gold and task coins (used for special exchanges).
#
# Taskmaster tiles (character must be here for task actions):
#   (1, 2)  — City, monsters tasks
#   (4, 13) — Forest, items tasks
#
# Task state lives on the character: task, task_type, task_progress, task_total.
# An empty task field means no active task.


def get_task_state(client, character_name: str) -> dict:
    """
    Return the character's current task state from GET /characters/{name}.
    Keys: task (item/monster code), task_type, task_progress, task_total.
    task='' means no active task.
    """
    response = client.get(f"/characters/{character_name}")
    response.raise_for_status()
    data = response.json()["data"]
    return {
        "task": data.get("task", ""),
        "task_type": data.get("task_type", ""),
        "task_progress": data.get("task_progress", 0),
        "task_total": data.get("task_total", 0),
    }


def has_active_task(task_state: dict) -> bool:
    """Return True if the character currently has an assigned task."""
    return bool(task_state.get("task"))


def is_task_complete(task_state: dict) -> bool:
    """
    Return True if the task objective is fully met (progress >= total).
    Does not check whether the character is at a Taskmaster — just state logic.
    """
    total = task_state.get("task_total", 0)
    progress = task_state.get("task_progress", 0)
    return total > 0 and progress >= total


def accept_task(client, character_name: str):
    """
    Accept a new task from the Taskmaster at the character's current tile.
    Returns raw response — 200 on success, 598 if no Taskmaster here,
    486 if character already has a task.
    """
    return client.post(f"/my/{character_name}/action/task/new")


def complete_task(client, character_name: str):
    """
    Turn in a completed task at the Taskmaster.
    Returns raw response — 200 on success, 487 if task not finished,
    598 if no Taskmaster on this tile.
    """
    return client.post(f"/my/{character_name}/action/task/complete")


def cancel_task(client, character_name: str):
    """
    Cancel the current task at a cost of 1 task coin.
    Returns raw response — 200 on success, 487 if no active task,
    478 if character lacks the required task coin to pay for cancellation.
    """
    return client.post(f"/my/{character_name}/action/task/cancel")


def parse_task_reward(response) -> dict | None:
    """
    Extract reward data from a successful task completion response.
    Returns data.rewards dict: {gold, items (list), task_coin (quantity)}.
    Returns None if not present.
    """
    try:
        return response.json()["data"]["rewards"]
    except (KeyError, TypeError, ValueError):
        return None


def parse_accepted_task(response) -> dict | None:
    """
    Extract the task assignment from a successful task/new response.
    Returns data.task dict: {code, type, total}.
    Returns None if not present.
    """
    try:
        return response.json()["data"]["task"]
    except (KeyError, TypeError, ValueError):
        return None
