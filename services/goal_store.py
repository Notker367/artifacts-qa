# SQLite storage for the goal system.
#
# Three tables:
#   goals        — user-level goals (collect, craft, equip, level)
#   tasks        — atomic executable steps assigned to characters
#   reservations — resource amounts locked by active goals/tasks
#
# Design rules:
#   - All writes go through this module. No raw SQL outside goal_store.py.
#   - Claim updates use atomic UPDATE WHERE status='open' to prevent
#     two characters grabbing the same task simultaneously.
#   - Schema is versioned via the schema_version table so future
#     migrations can be applied incrementally without manual surgery.
#   - DB file lives in data/goals.db (gitignored). Created on first use.

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "data" / "goals.db"
SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def _connect() -> sqlite3.Connection:
    """
    Open a connection to the goals DB with WAL mode enabled.
    WAL allows concurrent reads alongside a single writer — useful when a
    future web frontend reads goal state while the dispatcher is updating tasks.
    Row factory is set so rows behave like dicts.
    """
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS goals (
    id                   TEXT PRIMARY KEY,
    type                 TEXT NOT NULL,
    status               TEXT NOT NULL DEFAULT 'active',
    priority             INTEGER NOT NULL DEFAULT 100,

    target_item_code     TEXT,
    target_quantity      INTEGER,
    target_skill         TEXT,
    target_level         INTEGER,
    target_character     TEXT,

    -- eligibility fields stored as JSON arrays or NULL
    allowed_characters   TEXT,
    preferred_characters TEXT,
    assigned_character   TEXT,
    hard_assignment      INTEGER NOT NULL DEFAULT 0,

    parent_goal_id       TEXT,
    blocked_reason       TEXT,

    -- arbitrary extra data (JSON string)
    meta                 TEXT,

    created_at           TEXT NOT NULL,
    updated_at           TEXT NOT NULL,

    FOREIGN KEY (parent_goal_id) REFERENCES goals(id)
);

CREATE TABLE IF NOT EXISTS tasks (
    id                   TEXT PRIMARY KEY,
    goal_id              TEXT NOT NULL,
    type                 TEXT NOT NULL,
    status               TEXT NOT NULL DEFAULT 'open',

    character_name       TEXT,
    item_code            TEXT,
    quantity             INTEGER NOT NULL DEFAULT 0,

    allowed_characters   TEXT,
    preferred_characters TEXT,
    hard_assignment      INTEGER NOT NULL DEFAULT 0,

    claimed_by           TEXT,
    claimed_at           TEXT,
    -- dispatcher checks this; expired claims return to 'open'
    claim_timeout_seconds INTEGER NOT NULL DEFAULT 300,

    blocked_reason       TEXT,
    meta                 TEXT,

    created_at           TEXT NOT NULL,
    updated_at           TEXT NOT NULL,

    FOREIGN KEY (goal_id) REFERENCES goals(id)
);

CREATE TABLE IF NOT EXISTS reservations (
    id        TEXT PRIMARY KEY,
    goal_id   TEXT NOT NULL,
    task_id   TEXT,
    item_code TEXT NOT NULL,
    quantity  INTEGER NOT NULL,
    created_at TEXT NOT NULL,

    FOREIGN KEY (goal_id) REFERENCES goals(id)
);
"""


def init_db() -> None:
    """
    Create tables if they don't exist and stamp the schema version.
    Safe to call on every startup — CREATE TABLE IF NOT EXISTS is idempotent.
    """
    with _connect() as conn:
        conn.executescript(_SCHEMA)
        existing = conn.execute("SELECT version FROM schema_version").fetchone()
        if existing is None:
            conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
            logger.info("goal_store: schema v%d initialised at %s", SCHEMA_VERSION, DB_PATH)
        else:
            logger.debug("goal_store: schema v%d already present", existing["version"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _encode_list(value: list | None) -> str | None:
    """Encode a list to a JSON string for storage, or None if empty/absent."""
    if not value:
        return None
    return json.dumps(value)


def _decode_list(value: str | None) -> list | None:
    """Decode a stored JSON string back to a list, or None."""
    if value is None:
        return None
    return json.loads(value)


def _decode_meta(value: str | None) -> dict | None:
    if value is None:
        return None
    return json.loads(value)


def _row_to_goal(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["allowed_characters"] = _decode_list(d.get("allowed_characters"))
    d["preferred_characters"] = _decode_list(d.get("preferred_characters"))
    d["hard_assignment"] = bool(d.get("hard_assignment"))
    d["meta"] = _decode_meta(d.get("meta"))
    return d


def _row_to_task(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["allowed_characters"] = _decode_list(d.get("allowed_characters"))
    d["preferred_characters"] = _decode_list(d.get("preferred_characters"))
    d["hard_assignment"] = bool(d.get("hard_assignment"))
    d["meta"] = _decode_meta(d.get("meta"))
    return d


# ---------------------------------------------------------------------------
# Goal CRUD
# ---------------------------------------------------------------------------

def insert_goal(goal: dict) -> None:
    """Insert a new goal. Caller must provide all required fields."""
    now = _now()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO goals (
                id, type, status, priority,
                target_item_code, target_quantity,
                target_skill, target_level, target_character,
                allowed_characters, preferred_characters,
                assigned_character, hard_assignment,
                parent_goal_id, blocked_reason, meta,
                created_at, updated_at
            ) VALUES (
                :id, :type, :status, :priority,
                :target_item_code, :target_quantity,
                :target_skill, :target_level, :target_character,
                :allowed_characters, :preferred_characters,
                :assigned_character, :hard_assignment,
                :parent_goal_id, :blocked_reason, :meta,
                :created_at, :updated_at
            )
            """,
            {
                **goal,
                "allowed_characters": _encode_list(goal.get("allowed_characters")),
                "preferred_characters": _encode_list(goal.get("preferred_characters")),
                "hard_assignment": int(goal.get("hard_assignment", False)),
                "meta": json.dumps(goal["meta"]) if goal.get("meta") else None,
                "created_at": now,
                "updated_at": now,
            },
        )


def get_goal(goal_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
    return _row_to_goal(row) if row else None


def get_goals(status: str | None = None) -> list[dict]:
    """Return all goals, optionally filtered by status."""
    with _connect() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM goals WHERE status = ? ORDER BY priority, created_at",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM goals ORDER BY priority, created_at"
            ).fetchall()
    return [_row_to_goal(r) for r in rows]


def update_goal_status(goal_id: str, status: str, blocked_reason: str | None = None) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE goals SET status = ?, blocked_reason = ?, updated_at = ? WHERE id = ?",
            (status, blocked_reason, _now(), goal_id),
        )


# ---------------------------------------------------------------------------
# Task CRUD
# ---------------------------------------------------------------------------

def insert_task(task: dict) -> None:
    now = _now()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO tasks (
                id, goal_id, type, status,
                character_name, item_code, quantity,
                allowed_characters, preferred_characters, hard_assignment,
                claimed_by, claimed_at, claim_timeout_seconds,
                blocked_reason, meta,
                created_at, updated_at
            ) VALUES (
                :id, :goal_id, :type, :status,
                :character_name, :item_code, :quantity,
                :allowed_characters, :preferred_characters, :hard_assignment,
                :claimed_by, :claimed_at, :claim_timeout_seconds,
                :blocked_reason, :meta,
                :created_at, :updated_at
            )
            """,
            {
                **task,
                "allowed_characters": _encode_list(task.get("allowed_characters")),
                "preferred_characters": _encode_list(task.get("preferred_characters")),
                "hard_assignment": int(task.get("hard_assignment", False)),
                "meta": json.dumps(task["meta"]) if task.get("meta") else None,
                "claimed_by": task.get("claimed_by"),
                "claimed_at": task.get("claimed_at"),
                "claim_timeout_seconds": task.get("claim_timeout_seconds", 300),
                "blocked_reason": task.get("blocked_reason"),
                "created_at": now,
                "updated_at": now,
            },
        )


def get_tasks(goal_id: str | None = None, status: str | None = None) -> list[dict]:
    """Return tasks filtered by goal and/or status."""
    clauses = []
    params = []
    if goal_id:
        clauses.append("goal_id = ?")
        params.append(goal_id)
    if status:
        clauses.append("status = ?")
        params.append(status)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM tasks {where} ORDER BY created_at", params
        ).fetchall()
    return [_row_to_task(r) for r in rows]


def claim_task(task_id: str, character_name: str) -> bool:
    """
    Atomically claim an open task for a character.
    Returns True if the claim succeeded (row was open), False if someone else got there first.
    The WHERE status='open' guard prevents double-claiming in the sequential dispatch loop.
    """
    now = _now()
    with _connect() as conn:
        cursor = conn.execute(
            """
            UPDATE tasks
            SET status = 'claimed', claimed_by = ?, claimed_at = ?, updated_at = ?
            WHERE id = ? AND status = 'open'
            """,
            (character_name, now, now, task_id),
        )
    return cursor.rowcount == 1


def update_task_status(task_id: str, status: str, blocked_reason: str | None = None) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE tasks SET status = ?, blocked_reason = ?, updated_at = ? WHERE id = ?",
            (status, blocked_reason, _now(), task_id),
        )


def expire_stale_claims() -> int:
    """
    Return timed-out claimed tasks to 'open' so another character can pick them up.
    Called at the start of each planning cycle.
    Returns the number of tasks that were reset.
    """
    with _connect() as conn:
        cursor = conn.execute(
            """
            UPDATE tasks
            SET status = 'open', claimed_by = NULL, claimed_at = NULL, updated_at = ?
            WHERE status = 'claimed'
              AND (
                CAST((julianday(?) - julianday(claimed_at)) * 86400 AS INTEGER)
                > claim_timeout_seconds
              )
            """,
            (_now(), _now()),
        )
    if cursor.rowcount:
        logger.info("goal_store: expired %d stale claim(s)", cursor.rowcount)
    return cursor.rowcount


def sub_goal_exists(parent_goal_id: str, goal_type: str, item_code: str) -> bool:
    """
    Return True if an active sub-goal of this type for this item already exists
    under the given parent. Used by the planner to avoid spawning duplicate
    collect/craft sub-goals on every planning cycle.
    """
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT 1 FROM goals
            WHERE parent_goal_id = ? AND type = ? AND target_item_code = ?
              AND status = 'active'
            LIMIT 1
            """,
            (parent_goal_id, goal_type, item_code),
        ).fetchone()
    return row is not None


def task_exists(goal_id: str, task_type: str, item_code: str | None = None) -> bool:
    """
    Return True if an open or claimed task of this type already exists for the goal.
    Used by the planner to stay idempotent — no duplicate tasks per planning cycle.
    """
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT 1 FROM tasks
            WHERE goal_id = ? AND type = ?
              AND (item_code = ? OR ? IS NULL)
              AND status IN ('open', 'claimed', 'running')
            LIMIT 1
            """,
            (goal_id, task_type, item_code, item_code),
        ).fetchone()
    return row is not None


# ---------------------------------------------------------------------------
# Reservation CRUD
# ---------------------------------------------------------------------------

def reserve(reservation: dict) -> None:
    """Reserve a quantity of an item for a goal/task."""
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO reservations (id, goal_id, task_id, item_code, quantity, created_at)
            VALUES (:id, :goal_id, :task_id, :item_code, :quantity, :created_at)
            """,
            {**reservation, "created_at": _now()},
        )


def get_reserved_quantity(item_code: str) -> int:
    """Return total quantity of an item currently reserved across all active goals."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(quantity), 0) AS total FROM reservations WHERE item_code = ?",
            (item_code,),
        ).fetchone()
    return row["total"]


def get_all_reserved_quantities() -> dict:
    """
    Return {item_code: total_reserved_quantity} for all items with active reservations.
    Used by world_state to build a single reservation snapshot per planning cycle
    instead of calling get_reserved_quantity() N times.
    """
    with _connect() as conn:
        rows = conn.execute(
            "SELECT item_code, SUM(quantity) AS total FROM reservations GROUP BY item_code"
        ).fetchall()
    return {row["item_code"]: row["total"] for row in rows}


def get_active_task_quantity(goal_id: str, item_code: str) -> int:
    """
    Return total quantity already covered by open/claimed/running tasks for
    this goal and item. Planner subtracts this from needed quantity to avoid
    creating duplicate work when tasks are already in flight.
    """
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(quantity), 0) AS total
            FROM tasks
            WHERE goal_id = ? AND item_code = ?
              AND status IN ('open', 'claimed', 'running')
            """,
            (goal_id, item_code),
        ).fetchone()
    return row["total"]


def release_reservation(reservation_id: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM reservations WHERE id = ?", (reservation_id,))


def release_reservations_for_task(task_id: str) -> None:
    """Release reservations tied to a specific task when it completes or fails."""
    with _connect() as conn:
        conn.execute("DELETE FROM reservations WHERE task_id = ?", (task_id,))


def release_reservations_for_goal(goal_id: str) -> None:
    """Release all reservations when a goal is completed or failed."""
    with _connect() as conn:
        conn.execute("DELETE FROM reservations WHERE goal_id = ?", (goal_id,))
