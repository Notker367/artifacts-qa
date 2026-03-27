# Lazy item metadata cache for Artifacts MMO.
#
# Fetches item info from GET /items/{code} on first access and stores it in
# data/items.json. Subsequent reads come from the file — no API call.
# No TTL: recipes don't change mid-season. Delete data/items.json to force refresh.
#
# Used by: craft goal planner (recipe lookup), equip goal (slot detection).

import json
import logging
from pathlib import Path

from services.crafting import get_item_info as _fetch_item_info, get_recipe

logger = logging.getLogger(__name__)

CACHE_FILE = Path(__file__).parent.parent / "data" / "items.json"


def _load() -> dict:
    if not CACHE_FILE.exists():
        return {}
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save(cache: dict) -> None:
    CACHE_FILE.parent.mkdir(exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")


def get_cached_item(client, item_code: str) -> dict | None:
    """
    Return item metadata for item_code.
    Reads from data/items.json if present; fetches from API and caches on miss.
    Returns None if item doesn't exist (404).
    """
    cache = _load()
    if item_code in cache:
        return cache[item_code]

    logger.debug("item_cache: fetching %r from API", item_code)
    info = _fetch_item_info(client, item_code)
    if info:
        cache[item_code] = info
        _save(cache)
        logger.debug("item_cache: cached %r (type=%s)", item_code, info.get("type"))
    return info


def get_cached_recipe(client, item_code: str) -> list:
    """
    Return the crafting recipe for item_code as [{code, quantity}, ...].
    Returns empty list if item has no recipe or doesn't exist.
    """
    info = get_cached_item(client, item_code)
    return get_recipe(info) if info else []


def get_craft_skill(client, item_code: str) -> tuple[str | None, int]:
    """
    Return (craft_skill, required_level) for item_code.
    Returns (None, 0) if the item has no recipe.
    """
    info = get_cached_item(client, item_code)
    if not info:
        return None, 0
    craft = info.get("craft") or {}
    return craft.get("skill"), craft.get("level", 1)


def get_item_type(client, item_code: str) -> str | None:
    """Return the item's type string (weapon, helmet, ring, ...) or None."""
    info = get_cached_item(client, item_code)
    return info.get("type") if info else None
