# Character profile tests for Artifacts MMO.
# GET /characters/{name} is a read-only endpoint — no cooldown waits needed.
# These tests verify that the profile structure covers what downstream services need:
# skill levels for crafting decisions, stats for combat planning, equipment for loadout checks.

import logging

from services.character import (
    get_character_profile,
    get_skill_level,
    get_stat,
    get_equipment,
    has_skill_level,
    SKILL_NAMES,
    EQUIPMENT_SLOTS,
)

logger = logging.getLogger(__name__)


def test_get_character_profile_returns_expected_fields(client, character_name):
    """
    Profile must be a non-empty dict with the fields every downstream service depends on:
    identity (name, level), position (x, y), health (hp, max_hp), and gold.
    """
    profile = get_character_profile(client, character_name)

    assert isinstance(profile, dict), "profile must be a dict"
    assert profile, "profile must not be empty"

    required_fields = ("name", "level", "x", "y", "hp", "max_hp", "gold")
    for field in required_fields:
        assert field in profile, f"profile missing required field: {field!r}"

    logger.info(
        "profile: name=%s level=%d pos=(%d,%d) hp=%d/%d gold=%d",
        profile["name"],
        profile["level"],
        profile["x"],
        profile["y"],
        profile["hp"],
        profile["max_hp"],
        profile["gold"],
    )


def test_character_profile_has_skill_levels(client, character_name):
    """
    All 8 gathering/crafting skill levels must be present as non-negative integers.
    Artifacts stores them as {skill}_level fields — e.g. mining_level, cooking_level.
    These drive skill-aware crafting and resource selection.
    """
    profile = get_character_profile(client, character_name)

    for skill in SKILL_NAMES:
        level = get_skill_level(profile, skill)
        assert isinstance(level, int), (
            f"{skill}_level must be int, got {type(level).__name__}"
        )
        assert level >= 0, f"{skill}_level must be >= 0, got {level}"
        logger.info("skill: %s = %d", skill, level)


def test_character_profile_has_equipment_slots(client, character_name):
    """
    All standard equipment slots must be readable from the profile.
    Slot value is a string: item code if equipped, empty string if not.
    """
    profile = get_character_profile(client, character_name)
    equipment = get_equipment(profile)

    assert isinstance(equipment, dict), "equipment must be a dict"
    assert len(equipment) == len(EQUIPMENT_SLOTS), (
        f"equipment must have {len(EQUIPMENT_SLOTS)} slots, got {len(equipment)}"
    )

    for slot, item in equipment.items():
        assert isinstance(item, str), (
            f"slot {slot!r} must be a string, got {type(item).__name__}"
        )

    equipped = {slot: item for slot, item in equipment.items() if item}
    logger.info(
        "equipment: %d/%d slots occupied — %s",
        len(equipped),
        len(EQUIPMENT_SLOTS),
        list(equipped.keys()) or "none",
    )


def test_has_skill_level_threshold(client, character_name):
    """
    has_skill_level must correctly gate access based on actual character skill.
    Level 0 is always satisfied (every character meets that bar).
    A threshold above the current level must return False.
    """
    profile = get_character_profile(client, character_name)

    # Every character has at least level 0 in every skill
    for skill in SKILL_NAMES:
        assert has_skill_level(profile, skill, 0), (
            f"has_skill_level({skill!r}, 0) must be True for any character"
        )

    # A level-1000 threshold must not be satisfied
    for skill in SKILL_NAMES:
        assert not has_skill_level(profile, skill, 1000), (
            f"has_skill_level({skill!r}, 1000) must be False"
        )

    # Verify against actual skill level
    skill = "mining"
    current = get_skill_level(profile, skill)
    assert has_skill_level(profile, skill, current), (
        f"has_skill_level({skill!r}, {current}) must be True (matches current level)"
    )
    if current > 0:
        assert not has_skill_level(profile, skill, current + 1), (
            f"has_skill_level({skill!r}, {current + 1}) must be False (above current)"
        )

    logger.info("has_skill_level: mining=%d — thresholds verified", current)
