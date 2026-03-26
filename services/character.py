# Character profile helpers for Artifacts MMO.
# GET /characters/{name} is the single source of truth for character state:
# skill levels, base stats, equipment, position, cooldown, gold, inventory.
# get_character_profile() is the foundation for skill-aware crafting,
# resource selection, and multi-character dispatch decisions.

SKILL_NAMES = (
    "mining",
    "woodcutting",
    "fishing",
    "cooking",
    "weaponcrafting",
    "gearcrafting",
    "jewelrycrafting",
    "alchemy",
)

# All standard equipment slots in Artifacts MMO.
# A slot value is an item code string, or empty string if nothing is equipped.
EQUIPMENT_SLOTS = (
    "weapon_slot",
    "shield_slot",
    "helmet_slot",
    "body_armor_slot",
    "leg_armor_slot",
    "boots_slot",
    "ring1_slot",
    "ring2_slot",
    "amulet_slot",
    "artifact1_slot",
    "artifact2_slot",
    "artifact3_slot",
    "utility1_slot",
    "utility2_slot",
    "bag_slot",
)


def get_character_profile(client, character_name: str) -> dict:
    """
    Fetch full character state from GET /characters/{name}.
    Returns the raw data dict — single entry point for all downstream decisions
    about skills, stats, equipment, position, and cooldown state.
    Raises on non-2xx (e.g. 404 if character not found).
    """
    response = client.get(f"/characters/{character_name}")
    response.raise_for_status()
    return response.json()["data"]


def get_skill_level(profile: dict, skill: str) -> int:
    """
    Return the character's current level in the given skill.
    Artifacts stores skill levels as {skill}_level fields on the character.
    Returns 0 if the skill field is absent (safe default for level checks).
    """
    return profile.get(f"{skill}_level", 0)


def get_stat(profile: dict, stat: str) -> int:
    """
    Return a base stat value from the character profile by its API field name.
    Returns 0 if the field is absent.
    Callers should use the exact API field name (e.g. "max_hp", "haste").
    """
    return profile.get(stat, 0)


def get_equipment(profile: dict) -> dict:
    """
    Return a {slot: item_code} dict for all standard equipment slots.
    Slot value is an item code string, or empty string if nothing is equipped.
    Used to inspect loadout before planning crafting or combat scenarios.
    """
    return {slot: profile.get(slot, "") for slot in EQUIPMENT_SLOTS}


def has_skill_level(profile: dict, skill: str, min_level: int) -> bool:
    """
    Return True if the character's skill level is at least min_level.
    Use before triggering actions that require a minimum skill threshold
    (e.g. mining level 1 for copper, cooking level 5 for a recipe).
    """
    return get_skill_level(profile, skill) >= min_level
