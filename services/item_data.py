# Static mapping tables for resource drops and skills.
#
# Why static here instead of API-driven:
#   The full item recipe/source data lives in GET /items/{code} — that will
#   be loaded into a cache in the craft goal implementation (item 28).
#   For assignment scoring we only need "which skill does this task require?"
#   A static table is enough for that, loads instantly, and has no API cost.
#   When the item cache is added, the scorer can be updated to use it.
#
# ITEM_SOURCE: drop item_code → content_code of the resource tile that produces it.
#   Used by: planner (tile existence check), assignment (skill lookup, proximity).
#
# RESOURCE_SKILL: content_code → skill name required to gather it.
#   Used by: assignment scorer (skill level bonus).
#
# Add entries here as new resources are discovered or unlocked.

# drop item → resource tile content_code
ITEM_SOURCE: dict[str, str] = {
    # Mining
    "copper_ore":   "copper_rocks",
    "iron_ore":     "iron_rocks",
    "coal":         "coal_rocks",
    "gold_ore":     "gold_rocks",
    "mithril_ore":  "mithril_rocks",

    # Woodcutting
    "ash_wood":     "ash_tree",
    "birch_wood":   "birch_tree",
    "spruce_wood":  "spruce_tree",
    "maple_wood":   "maple_tree",

    # Fishing
    "gudgeon":      "gudgeon_spot",
    "shrimp":       "shrimp_spot",
    "salmon":       "salmon_spot",
    "trout":        "trout_spot",
    "bass":         "bass_spot",

    # Alchemy
    "sunflower":    "sunflower_field",
    "glowstem":     "glowstem",
    "nettle":       "nettle",
    "torch_cactus": "torch_cactus",
}

# resource tile content_code → gathering skill
RESOURCE_SKILL: dict[str, str] = {
    # Mining
    "copper_rocks":  "mining",
    "iron_rocks":    "mining",
    "coal_rocks":    "mining",
    "gold_rocks":    "mining",
    "mithril_rocks": "mining",

    # Woodcutting
    "ash_tree":     "woodcutting",
    "birch_tree":   "woodcutting",
    "spruce_tree":  "woodcutting",
    "maple_tree":   "woodcutting",

    # Fishing
    "gudgeon_spot":  "fishing",
    "shrimp_spot":   "fishing",
    "salmon_spot":   "fishing",
    "trout_spot":    "fishing",
    "bass_spot":     "fishing",

    # Alchemy
    "sunflower_field": "alchemy",
    "glowstem":        "alchemy",
    "nettle":          "alchemy",
    "torch_cactus":    "alchemy",

    # Combat — content_code is the monster code
    "chicken":     "combat",
    "cow":         "combat",
    "green_slime": "combat",
    "wolf":        "combat",
}


# Primary drop item per resource content_code (reverse of ITEM_SOURCE).
# Used by: level goal planner — resolves "what item does this resource drop?"
# so it can create gather tasks using existing task infrastructure.
RESOURCE_DROP: dict[str, str] = {
    "copper_rocks":    "copper_ore",
    "iron_rocks":      "iron_ore",
    "coal_rocks":      "coal",
    "gold_rocks":      "gold_ore",
    "mithril_rocks":   "mithril_ore",
    "ash_tree":        "ash_wood",
    "birch_tree":      "birch_wood",
    "spruce_tree":     "spruce_wood",
    "maple_tree":      "maple_wood",
    "gudgeon_spot":    "gudgeon",
    "shrimp_spot":     "shrimp",
    "salmon_spot":     "salmon",
    "trout_spot":      "trout",
    "bass_spot":       "bass",
    "sunflower_field": "sunflower",
    "glowstem":        "glowstem",
    "nettle":          "nettle",
    "torch_cactus":    "torch_cactus",
}

# Best training resource per skill (level 1, widely available).
# Used by: level goal planner — pick what to gather/fight for XP.
# content_code for monsters is used directly (find_content searches all types).
SKILL_TRAIN_RESOURCE: dict[str, str] = {
    "mining":        "copper_rocks",
    "woodcutting":   "ash_tree",
    "fishing":       "gudgeon_spot",
    "alchemy":       "sunflower_field",
    "cooking":       None,              # requires ingredients; not supported yet
    "combat":        "chicken",         # monster content_code
    "weaponcrafting":  None,            # skill raised by crafting, not gathering
    "gearcrafting":    None,
    "jewelrycrafting": None,
}

# Workshop content_code per crafting skill, as it appears in the map cache.
# Run `python scripts/discover_map.py --all` to verify exact codes for your server.
# Planner will block the goal with a clear message if the code isn't found in cache.
WORKSHOP_CONTENT_CODE: dict[str, str] = {
    "weaponcrafting":   "weaponcrafting",
    "gearcrafting":     "gearcrafting",
    "jewelrycrafting":  "jewelrycrafting",
    "cooking":          "cooking",
    "alchemy":          "alchemy",
    "mining":           "mining",       # smelting forge
}


def resource_for_item(item_code: str) -> str | None:
    """Return the resource tile content_code that drops this item, or None."""
    return ITEM_SOURCE.get(item_code)


def skill_for_resource(resource_code: str) -> str | None:
    """Return the skill name needed to gather from this resource tile, or None."""
    return RESOURCE_SKILL.get(resource_code)


def skill_for_item(item_code: str) -> str | None:
    """Return the skill needed to gather item_code, walking through ITEM_SOURCE."""
    resource = resource_for_item(item_code)
    if resource is None:
        return None
    return skill_for_resource(resource)


def drop_for_resource(resource_code: str) -> str | None:
    """Return the primary drop item_code for a resource tile content_code."""
    return RESOURCE_DROP.get(resource_code)


def train_resource_for_skill(skill: str) -> str | None:
    """Return the default resource content_code to use for training a skill."""
    return SKILL_TRAIN_RESOURCE.get(skill)


def workshop_code_for_skill(craft_skill: str) -> str | None:
    """Return the map content_code for the workshop tile of a craft skill."""
    return WORKSHOP_CONTENT_CODE.get(craft_skill)
