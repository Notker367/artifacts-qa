# Map tile cache for Artifacts MMO.
# Fetches all tiles from GET /maps and stores them locally as JSON.
# Avoids repeated API calls for static world data that rarely changes mid-season.
#
# Cache format (data/maps.json):
#   {
#     "fetched_at": "2026-03-27T12:00:00+00:00",
#     "version": 1,
#     "total": 1428,
#     "tiles": [
#       {
#         "map_id": 26, "name": "Mine", "skin": "mine3_4",
#         "x": 3, "y": -5, "layer": "underground",
#         "access_type": "standard",
#         "content_type": "resource",
#         "content_code": "gold_rocks"
#       },
#       ...
#     ]
#   }
#
# Raw API tile structure (interactions.content and access.type are flattened):
#   {
#     "map_id": int, "name": str, "skin": str,
#     "x": int, "y": int, "layer": "overworld"|"underground",
#     "access": {"type": "standard"|"blocked"|..., "conditions": []},
#     "interactions": {"content": {"type": str, "code": str} | null, "transition": null}
#   }
#
# Errors that should trigger cache invalidation:
#   - 598 NO_RESOURCE_ON_TILE: resource removed from a tile after a game update or season reset
#   - 404 returned by /maps: tile no longer exists
#
# Typical usage:
#   cache = get_map_cache(client)
#   tiles = find_tiles(cache, content_type="resource", content_code="ash_tree")
#   tile  = find_tile_at(cache, x=2, y=0)
#
#   # after a 598 error:
#   invalidate_cache()
#   cache = get_map_cache(client, force=True)

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

# Cache lives in data/ at project root — one level above services/
_PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = _PROJECT_ROOT / "data"
CACHE_FILE = DATA_DIR / "maps.json"

# Bump when the stored format changes so old files are automatically discarded
CACHE_VERSION = 1

# Map data is stable within a season (~4 months); 24h TTL is conservative
DEFAULT_MAX_AGE_HOURS = 24


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _flatten_tile(raw: dict) -> dict:
    """
    Flatten a raw API tile into a simpler dict for storage and querying.
    Pulls access.type and interactions.content.* up to top-level fields.
    Tiles with no content (empty map squares) get content_type=None, content_code=None.
    """
    content = (raw.get("interactions") or {}).get("content") or {}
    return {
        "map_id":       raw.get("map_id"),
        "name":         raw.get("name"),
        "skin":         raw.get("skin"),
        "x":            raw.get("x"),
        "y":            raw.get("y"),
        "layer":        raw.get("layer"),
        "access_type":  (raw.get("access") or {}).get("type"),
        "content_type": content.get("type"),
        "content_code": content.get("code"),
    }


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

def fetch_all_tiles(client, content_type: str = None) -> tuple:
    """
    Paginate through GET /maps and return (tiles, total).
    Uses size=100 to minimise API calls (~15 requests for 1428 tiles).
    Pass content_type to fetch only a filtered subset (e.g. "resource").
    Returns: (list of flattened tile dicts, total tile count from API)
    """
    all_tiles = []
    page = 1
    total = None

    while True:
        params = {"page": page, "size": 100}
        if content_type:
            params["content_type"] = content_type

        response = client.get("/maps", params=params)
        response.raise_for_status()

        body = response.json()
        if total is None:
            total = body.get("total", 0)

        data = body.get("data", [])
        if not data:
            break

        all_tiles.extend(_flatten_tile(t) for t in data)
        logger.debug("fetch_all_tiles: page %d — %d tiles fetched so far", page, len(all_tiles))

        pages = body.get("pages", 1)
        if page >= pages:
            break
        page += 1

    logger.info("fetch_all_tiles: done — %d tiles (api total=%s)", len(all_tiles), total)
    return all_tiles, total or len(all_tiles)


# ---------------------------------------------------------------------------
# Load / save
# ---------------------------------------------------------------------------

def load_map_cache() -> dict | None:
    """
    Read data/maps.json and return the cache dict.
    Returns None if the file does not exist or the version does not match.
    """
    if not CACHE_FILE.exists():
        logger.debug("load_map_cache: %s not found", CACHE_FILE)
        return None

    with CACHE_FILE.open(encoding="utf-8") as fh:
        cache = json.load(fh)

    if cache.get("version") != CACHE_VERSION:
        logger.warning(
            "load_map_cache: version mismatch (got %s, want %s) — discarding",
            cache.get("version"), CACHE_VERSION,
        )
        return None

    logger.debug("load_map_cache: %d tiles loaded from %s", len(cache.get("tiles", [])), CACHE_FILE)
    return cache


def save_map_cache(tiles: list, total: int) -> None:
    """
    Write tiles to data/maps.json with a fetched_at UTC timestamp.
    Creates data/ if it does not exist yet.
    """
    DATA_DIR.mkdir(exist_ok=True)

    cache = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "version": CACHE_VERSION,
        "total": total,
        "tiles": tiles,
    }

    with CACHE_FILE.open("w", encoding="utf-8") as fh:
        json.dump(cache, fh, ensure_ascii=False, indent=2)

    logger.info("save_map_cache: %d tiles written to %s", len(tiles), CACHE_FILE)


# ---------------------------------------------------------------------------
# Staleness and invalidation
# ---------------------------------------------------------------------------

def is_cache_stale(cache: dict, max_age_hours: float = DEFAULT_MAX_AGE_HOURS) -> bool:
    """
    Return True if the cache is older than max_age_hours.
    A missing or unparseable fetched_at is treated as stale.
    """
    fetched_at_str = cache.get("fetched_at")
    if not fetched_at_str:
        return True

    try:
        fetched_at = datetime.fromisoformat(fetched_at_str)
    except ValueError:
        return True

    age = datetime.now(timezone.utc) - fetched_at
    stale = age > timedelta(hours=max_age_hours)
    if stale:
        logger.debug("is_cache_stale: cache age %.1fh exceeds limit %.1fh", age.total_seconds() / 3600, max_age_hours)
    return stale


def invalidate_cache() -> None:
    """
    Delete the cache file to force a fresh fetch on the next get_map_cache() call.
    Call this after receiving a 598 NO_RESOURCE_ON_TILE or a 404 on a cached tile —
    both indicate that the world state has diverged from what we stored.
    """
    if CACHE_FILE.exists():
        CACHE_FILE.unlink()
        logger.info("invalidate_cache: %s removed", CACHE_FILE)
    else:
        logger.debug("invalidate_cache: nothing to remove")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def get_map_cache(client, force: bool = False, content_type: str = None) -> dict:
    """
    Return the map cache dict (with a 'tiles' list ready for querying).
    Loads from file when the cache is present and fresh.
    Fetches from API when the cache is missing, stale, or force=True.

    Args:
        client:       ArtifactsClient instance (used only when a fetch is needed)
        force:        bypass the file cache and always fetch fresh data from API
        content_type: when fetching, filter tiles to this content type only
                      (use None to fetch the full map — recommended for long-lived cache)
    """
    if not force:
        cache = load_map_cache()
        if cache is not None and not is_cache_stale(cache):
            logger.debug("get_map_cache: cache is fresh (%d tiles)", len(cache["tiles"]))
            return cache
        reason = "missing" if cache is None else "stale"
        logger.info("get_map_cache: cache %s — fetching from API", reason)
    else:
        logger.info("get_map_cache: force=True — fetching from API")

    tiles, total = fetch_all_tiles(client, content_type=content_type)
    save_map_cache(tiles, total)
    return load_map_cache()


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def find_content(cache: dict, code: str) -> list:
    """
    Return all tiles with this content_code, regardless of content_type.
    Use when you know the code but not the type — works for resources, monsters, buildings.
    Example: find_content(cache, "chicken")      → monster tile(s)
             find_content(cache, "ash_tree")     → resource tile(s)
             find_content(cache, "bank")         → bank tile(s)
    """
    return [t for t in cache.get("tiles", []) if t.get("content_code") == code]


def find_tiles(cache: dict, content_type: str, content_code: str = None) -> list:
    """
    Return all tiles matching content_type, optionally narrowed by content_code.
    Example: find_tiles(cache, "resource", "ash_tree") → list of ash tree tile dicts.
    Example: find_tiles(cache, "monster") → all monster tiles.
    """
    tiles = cache.get("tiles", [])
    result = [t for t in tiles if t.get("content_type") == content_type]
    if content_code is not None:
        result = [t for t in result if t.get("content_code") == content_code]
    return result


def find_tile_at(cache: dict, x: int, y: int) -> dict | None:
    """
    Return the tile at coordinates (x, y), or None if not found in cache.
    Useful for validating known hardcoded coordinates against live map data.
    """
    for tile in cache.get("tiles", []):
        if tile.get("x") == x and tile.get("y") == y:
            return tile
    return None
