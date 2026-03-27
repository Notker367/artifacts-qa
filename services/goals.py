# Goal and PlannedTask models for the goal system.
#
# Goals are user-level intentions ("collect 200 copper_ore").
# PlannedTasks are atomic executable steps for one character ("gather copper_ore × 80").
#
# These are plain dataclasses — no ORM, no magic.
# Serialization to/from dicts happens here so goal_store.py stays a thin DB layer.
#
# Status lifecycle:
#   Goal:        active → completed | blocked | failed
#   PlannedTask: open → claimed → running → done | blocked | failed
#
# Eligibility fields control who can execute a task:
#   allowed_characters  — only these characters may take the task (None = anyone)
#   preferred_characters — these get a suitability score bonus
#   assigned_character  — dispatcher picks this one first
#   hard_assignment     — only assigned_character may take the task, no fallback

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Status constants
# ---------------------------------------------------------------------------

class GoalStatus:
    ACTIVE    = "active"
    COMPLETED = "completed"
    BLOCKED   = "blocked"
    FAILED    = "failed"


class TaskStatus:
    OPEN    = "open"
    CLAIMED = "claimed"
    RUNNING = "running"
    DONE    = "done"
    BLOCKED = "blocked"
    FAILED  = "failed"


# ---------------------------------------------------------------------------
# Goal types
# ---------------------------------------------------------------------------

class GoalType:
    COLLECT = "collect"  # gather item X in quantity N and deliver to bank
    CRAFT   = "craft"    # craft item X in quantity N
    EQUIP   = "equip"    # equip item X on target_character
    LEVEL   = "level"    # level target_skill to target_level on target_character


# ---------------------------------------------------------------------------
# Task types
# ---------------------------------------------------------------------------

class TaskType:
    GATHER   = "gather"    # move to resource tile and gather
    DEPOSIT  = "deposit"   # move to bank and deposit items
    WITHDRAW = "withdraw"  # move to bank and withdraw items
    CRAFT    = "craft"     # move to workshop and craft
    EQUIP    = "equip"     # equip item (no tile required)
    FIGHT    = "fight"     # move to monster tile and fight


# ---------------------------------------------------------------------------
# Goal dataclass
# ---------------------------------------------------------------------------

@dataclass
class Goal:
    type:   str
    status: str = GoalStatus.ACTIVE

    # What the goal wants to achieve
    target_item_code: str | None = None
    target_quantity:  int | None = None
    target_skill:     str | None = None
    target_level:     int | None = None
    # Which character the result applies to (equip/level goals)
    target_character: str | None = None

    # Eligibility
    allowed_characters:   list[str] | None = None
    preferred_characters: list[str] | None = None
    assigned_character:   str | None = None
    hard_assignment:      bool = False

    # Dependency chain
    parent_goal_id: str | None = None
    blocked_reason: str | None = None

    priority: int = 100
    meta: dict | None = None

    # Set on creation, not by caller
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict:
        return {
            "id":                   self.id,
            "type":                 self.type,
            "status":               self.status,
            "priority":             self.priority,
            "target_item_code":     self.target_item_code,
            "target_quantity":      self.target_quantity,
            "target_skill":         self.target_skill,
            "target_level":         self.target_level,
            "target_character":     self.target_character,
            "allowed_characters":   self.allowed_characters,
            "preferred_characters": self.preferred_characters,
            "assigned_character":   self.assigned_character,
            "hard_assignment":      self.hard_assignment,
            "parent_goal_id":       self.parent_goal_id,
            "blocked_reason":       self.blocked_reason,
            "meta":                 self.meta,
        }

    @staticmethod
    def collect(item_code: str, quantity: int, **kwargs) -> "Goal":
        """Shorthand: collect item_code × quantity into bank."""
        return Goal(type=GoalType.COLLECT, target_item_code=item_code,
                    target_quantity=quantity, **kwargs)

    @staticmethod
    def craft(item_code: str, quantity: int, **kwargs) -> "Goal":
        """Shorthand: craft item_code × quantity."""
        return Goal(type=GoalType.CRAFT, target_item_code=item_code,
                    target_quantity=quantity, **kwargs)

    @staticmethod
    def equip(item_code: str, character_name: str, **kwargs) -> "Goal":
        """Shorthand: equip item_code on character_name (hard-assigned by default)."""
        return Goal(type=GoalType.EQUIP, target_item_code=item_code,
                    target_character=character_name,
                    assigned_character=character_name, hard_assignment=True, **kwargs)

    @staticmethod
    def level(skill: str, target_level: int, character_name: str, **kwargs) -> "Goal":
        """Shorthand: level skill to target_level on character_name (hard-assigned)."""
        return Goal(type=GoalType.LEVEL, target_skill=skill,
                    target_level=target_level, target_character=character_name,
                    assigned_character=character_name, hard_assignment=True, **kwargs)


# ---------------------------------------------------------------------------
# PlannedTask dataclass
# ---------------------------------------------------------------------------

@dataclass
class PlannedTask:
    goal_id:   str
    type:      str
    status:    str = TaskStatus.OPEN

    character_name: str | None = None
    item_code:      str | None = None
    quantity:       int = 0

    # Eligibility (inherited from parent goal or set explicitly)
    allowed_characters:   list[str] | None = None
    preferred_characters: list[str] | None = None
    hard_assignment:      bool = False

    # Claim state — managed by dispatcher, not planner
    claimed_by:            str | None = None
    claimed_at:            str | None = None
    claim_timeout_seconds: int = 300

    blocked_reason: str | None = None
    meta: dict | None = None

    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict:
        return {
            "id":                    self.id,
            "goal_id":               self.goal_id,
            "type":                  self.type,
            "status":                self.status,
            "character_name":        self.character_name,
            "item_code":             self.item_code,
            "quantity":              self.quantity,
            "allowed_characters":    self.allowed_characters,
            "preferred_characters":  self.preferred_characters,
            "hard_assignment":       self.hard_assignment,
            "claimed_by":            self.claimed_by,
            "claimed_at":            self.claimed_at,
            "claim_timeout_seconds": self.claim_timeout_seconds,
            "blocked_reason":        self.blocked_reason,
            "meta":                  self.meta,
        }


# ---------------------------------------------------------------------------
# Convenience constructors for common task shapes
# ---------------------------------------------------------------------------

def make_gather_task(goal_id: str, item_code: str, quantity: int,
                     allowed: list[str] | None = None,
                     preferred: list[str] | None = None) -> PlannedTask:
    return PlannedTask(
        goal_id=goal_id, type=TaskType.GATHER,
        item_code=item_code, quantity=quantity,
        allowed_characters=allowed, preferred_characters=preferred,
    )


def make_craft_task(goal_id: str, item_code: str, quantity: int,
                    character_name: str | None = None,
                    allowed: list[str] | None = None) -> PlannedTask:
    return PlannedTask(
        goal_id=goal_id, type=TaskType.CRAFT,
        item_code=item_code, quantity=quantity,
        character_name=character_name, allowed_characters=allowed,
    )


def make_equip_task(goal_id: str, item_code: str,
                    character_name: str) -> PlannedTask:
    """Equip tasks are always hard-assigned — only target character should equip."""
    return PlannedTask(
        goal_id=goal_id, type=TaskType.EQUIP,
        item_code=item_code, character_name=character_name,
        hard_assignment=True,
    )


def make_fight_task(goal_id: str, monster_code: str, count: int,
                    allowed: list[str] | None = None) -> PlannedTask:
    """
    Fight task: fight monster_code `count` times.
    item_code holds the monster content_code (semantic re-use of the field).
    Used by level goal for combat training.
    """
    return PlannedTask(
        goal_id=goal_id, type=TaskType.FIGHT,
        item_code=monster_code, quantity=count,
        allowed_characters=allowed,
    )
