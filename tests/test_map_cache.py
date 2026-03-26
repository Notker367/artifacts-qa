# Map cache tests for Artifacts MMO.
# map_cache.py has two distinct concerns:
#   1. Pure logic: stale check, flatten, find_content — tested without API or file I/O
#   2. API access: GET /maps pagination and response structure — tested as smoke
#
# No stateful game actions here — the map is read-only public data.

import logging
from datetime import datetime, timezone, timedelta

from services.map_cache import (
    is_cache_stale,
    find_content,
    find_tiles,
    find_tile_at,
    _flatten_tile,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pure logic tests — no API, no file I/O
# ---------------------------------------------------------------------------

def test_is_cache_stale_fresh():
    """Cache with fetched_at one minute ago must not be stale under default TTL (24h)."""
    cache = {"fetched_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()}
    assert not is_cache_stale(cache), "1-minute-old cache must be fresh"


def test_is_cache_stale_old():
    """Cache older than max_age_hours must be stale."""
    cache = {"fetched_at": (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()}
    assert is_cache_stale(cache), "25-hour-old cache must be stale"


def test_is_cache_stale_missing_field():
    """Cache with no fetched_at must be treated as stale."""
    assert is_cache_stale({}), "cache without fetched_at must be stale"
    assert is_cache_stale({"fetched_at": None}), "cache with fetched_at=None must be stale"


def test_is_cache_stale_custom_ttl():
    """Custom max_age_hours must be respected."""
    cache = {"fetched_at": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()}
    assert is_cache_stale(cache, max_age_hours=1), "2h cache must be stale with 1h TTL"
    assert not is_cache_stale(cache, max_age_hours=3), "2h cache must be fresh with 3h TTL"


def test_flatten_tile_with_content():
    """_flatten_tile must extract content_type and content_code to top level."""
    raw = {
        "map_id": 26, "name": "Mine", "skin": "mine3_4",
        "x": 3, "y": -5, "layer": "underground",
        "access": {"type": "standard", "conditions": []},
        "interactions": {"content": {"type": "resource", "code": "gold_rocks"}, "transition": None},
    }
    tile = _flatten_tile(raw)
    assert tile["content_type"] == "resource"
    assert tile["content_code"] == "gold_rocks"
    assert tile["access_type"] == "standard"
    assert tile["x"] == 3 and tile["y"] == -5


def test_flatten_tile_null_content():
    """_flatten_tile must set content_type and content_code to None for empty tiles."""
    raw = {
        "map_id": 1, "name": "Forest", "skin": "forest_3",
        "x": -5, "y": -5, "layer": "overworld",
        "access": {"type": "standard", "conditions": []},
        "interactions": {"content": None, "transition": None},
    }
    tile = _flatten_tile(raw)
    assert tile["content_type"] is None
    assert tile["content_code"] is None


def _make_cache(*tiles) -> dict:
    """Build a minimal cache dict from tile keyword args for query tests."""
    return {"tiles": list(tiles)}


def test_find_content_by_code():
    """find_content must return all tiles with matching content_code regardless of type."""
    cache = _make_cache(
        {"x": 2, "y": 0, "content_type": "resource", "content_code": "copper_rocks"},
        {"x": 0, "y": 1, "content_type": "monster",  "content_code": "chicken"},
        {"x": 4, "y": 1, "content_type": "bank",     "content_code": "bank"},
    )
    assert len(find_content(cache, "copper_rocks")) == 1
    assert len(find_content(cache, "chicken")) == 1
    assert len(find_content(cache, "bank")) == 1
    assert find_content(cache, "nonexistent") == []


def test_find_content_multiple_tiles():
    """find_content must return all tiles when a code appears at more than one location."""
    cache = _make_cache(
        {"x": -1, "y": 0, "content_type": "resource", "content_code": "ash_tree"},
        {"x":  6, "y": 1, "content_type": "resource", "content_code": "ash_tree"},
    )
    result = find_content(cache, "ash_tree")
    assert len(result) == 2
    coords = {(t["x"], t["y"]) for t in result}
    assert (-1, 0) in coords and (6, 1) in coords


def test_find_tiles_by_type():
    """find_tiles must filter by content_type and optionally by content_code."""
    cache = _make_cache(
        {"x": 2, "y": 0, "content_type": "resource", "content_code": "copper_rocks"},
        {"x": 0, "y": 1, "content_type": "monster",  "content_code": "chicken"},
        {"x": 1, "y": 7, "content_type": "resource", "content_code": "iron_rocks"},
    )
    resources = find_tiles(cache, "resource")
    assert len(resources) == 2

    copper = find_tiles(cache, "resource", "copper_rocks")
    assert len(copper) == 1 and copper[0]["x"] == 2

    assert find_tiles(cache, "monster", "chicken")[0]["x"] == 0
    assert find_tiles(cache, "resource", "gold_rocks") == []


def test_find_tile_at():
    """find_tile_at must return the tile at (x, y) or None if absent."""
    cache = _make_cache(
        {"x": 2, "y": 0, "content_type": "resource", "content_code": "copper_rocks"},
        {"x": 4, "y": 1, "content_type": "bank",     "content_code": "bank"},
    )
    tile = find_tile_at(cache, 2, 0)
    assert tile is not None and tile["content_code"] == "copper_rocks"

    assert find_tile_at(cache, 99, 99) is None


# ---------------------------------------------------------------------------
# Smoke tests — read-only API calls, no state changes
# ---------------------------------------------------------------------------

def test_maps_api_returns_paginated_data(client):
    """
    GET /maps?page=1&size=5 must return 200 with a data list and pagination fields.
    Verifies the data source used by the map cache is reachable and well-formed.
    """
    response = client.get("/maps", params={"page": 1, "size": 5})
    assert response.status_code == 200

    body = response.json()
    assert "data" in body, "response must have 'data' key"
    assert "total" in body, "response must have 'total' key"
    assert "pages" in body, "response must have 'pages' key"
    assert body["total"] > 0, "total must be > 0"

    logger.info("GET /maps: total=%d pages=%d", body["total"], body["pages"])


def test_maps_api_tile_structure(client):
    """
    Each tile in GET /maps must have the fields map_cache._flatten_tile depends on.
    Catches silent API schema changes before they break the cache layer.
    """
    response = client.get("/maps", params={"page": 1, "size": 1})
    assert response.status_code == 200

    tile = response.json()["data"][0]
    for field in ("x", "y", "layer", "access", "interactions"):
        assert field in tile, f"tile missing required field: {field!r}"

    # interactions.content may be null (empty tile) — that is valid
    interactions = tile["interactions"]
    assert isinstance(interactions, dict), "interactions must be a dict"
    assert "content" in interactions, "interactions must have 'content' key"

    logger.info(
        "tile sample: (%d, %d) layer=%s content=%s",
        tile["x"], tile["y"], tile["layer"], interactions.get("content"),
    )


def test_maps_api_content_type_filter(client):
    """
    GET /maps?content_type=resource must return only resource tiles.
    Verifies that the filter used by fetch_all_tiles works correctly.
    """
    response = client.get("/maps", params={"content_type": "resource", "page": 1, "size": 10})
    assert response.status_code == 200

    tiles = response.json()["data"]
    assert tiles, "resource filter must return at least one tile"

    for tile in tiles:
        content = (tile.get("interactions") or {}).get("content")
        assert content is not None, "resource-filtered tile must have non-null content"
        assert content.get("type") == "resource", (
            f"content_type filter returned non-resource tile: {content}"
        )

    logger.info("resource tiles (sample): %d returned", len(tiles))
