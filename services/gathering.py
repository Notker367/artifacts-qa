# Gathering helpers for Artifacts MMO.
# Gathering is a stateful action — it consumes a cooldown slot and modifies inventory.
# The character must be on a map tile with a gatherable resource for 200 to occur.
#
# 598 NO_RESOURCE_ON_TILE means the tile has no resource — either the character moved
# to the wrong tile, or the game world changed since the map cache was built.
# In the latter case, the cache is invalidated so the next lookup fetches fresh data.

from services.errors import NO_RESOURCE_ON_TILE
from services.map_cache import invalidate_cache


def gather(client, character_name: str):
    """
    Send the gathering action at the character's current location.
    Returns the raw response — callers handle 200/497/499 based on context.
    No body needed; the server determines what resource is at the current tile.

    On 598 (no resource here): invalidates the map cache so the next dispatch
    cycle fetches fresh tile data rather than re-navigating to a dead tile.
    """
    response = client.post(f"/my/{character_name}/action/gathering")
    if response.status_code == NO_RESOURCE_ON_TILE:
        # Tile was in cache as a resource tile but the game world disagrees.
        # Drop the cache so get_map_cache() fetches fresh data on the next cycle.
        invalidate_cache()
    return response


def parse_gathered_items(response) -> list:
    """
    Extract the list of items collected from a successful gather response.
    Artifacts returns items under data.details.items as [{"code": str, "quantity": int}].
    Returns an empty list if the response has no items (e.g. cooldown or error responses).
    """
    try:
        return response.json()["data"]["details"]["items"]
    except (KeyError, TypeError, ValueError):
        return []
