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
