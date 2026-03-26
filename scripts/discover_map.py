#!/usr/bin/env python3
"""
Discover and display resource tile coordinates from the cached map.

Fetches all map tiles from the API (if cache is missing or stale) and prints
the coordinates for each resource code relevant to our gathering roles.
Run this once to populate data/maps.json and confirm tile coordinates
before wiring them into scenario.py.

Usage:
    python scripts/discover_map.py             # use cache if fresh (< 24h)
    python scripts/discover_map.py --refresh   # force fresh fetch from API
    python scripts/discover_map.py --all       # also show monster and workshop tiles
"""

import sys
import argparse
import logging
from pathlib import Path

# Allow imports from project root when running as a standalone script
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from clients.artifacts_client import ArtifactsClient
from services.map_cache import get_map_cache, find_tiles, CACHE_FILE

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Resource codes grouped by gathering role.
# Each code maps to one or more tiles — we print all coordinates.
ROLE_RESOURCES = {
    "mining": [
        "copper_rocks",
        "iron_rocks",
        "coal_rocks",
        "gold_rocks",
        "mithril_rocks",
        "adamantite_rocks",
    ],
    "woodcutting": [
        "ash_tree",
        "birch_tree",
        "spruce_tree",
        "maple_tree",
        "dead_tree",
        "palm_tree",
    ],
    "fishing": [
        "gudgeon_spot",
        "shrimp_spot",
        "salmon_spot",
        "trout_spot",
        "bass_spot",
        "swordfish_spot",
    ],
    "alchemy": [
        "sunflower_field",
        "glowstem",
        "nettle",
        "torch_cactus",
    ],
}

# Non-gathering content types shown only with --all
EXTRA_TYPES = ["monster", "workshop", "bank", "tasks_master", "grand_exchange"]


def _coords(tiles: list) -> str:
    return "  ".join(f"({t['x']}, {t['y']})" for t in tiles)


def print_resources(cache: dict) -> None:
    for role, codes in ROLE_RESOURCES.items():
        print(f"\n=== {role} ===")
        for code in codes:
            matches = find_tiles(cache, "resource", code)
            if matches:
                print(f"  {code:<22} {_coords(matches)}")


def print_all_content_types(cache: dict) -> None:
    for ctype in EXTRA_TYPES:
        tiles = find_tiles(cache, ctype)
        if not tiles:
            continue
        print(f"\n=== {ctype} ===")
        for t in tiles:
            code = t.get("content_code", "")
            print(f"  ({t['x']:>3}, {t['y']:>3})  {code}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover resource tile coordinates")
    parser.add_argument("--refresh", action="store_true", help="Force fresh fetch from API")
    parser.add_argument("--all", action="store_true", help="Also show monster/workshop/bank tiles")
    args = parser.parse_args()

    import os
    token = os.getenv("ARTIFACTS_TOKEN")
    if not token:
        print("ERROR: ARTIFACTS_TOKEN env var not set")
        sys.exit(1)
    client = ArtifactsClient(token)

    if not args.refresh and CACHE_FILE.exists():
        print(f"[cache] loading from {CACHE_FILE}")
    else:
        print("[cache] fetching all map tiles from API (this makes ~15 requests)...")

    cache = get_map_cache(client, force=args.refresh)
    tiles = cache.get("tiles", [])
    fetched_at = cache.get("fetched_at", "unknown")

    print(f"[cache] {len(tiles)} tiles | fetched_at: {fetched_at}\n")

    print_resources(cache)

    if args.all:
        print_all_content_types(cache)

    print()


if __name__ == "__main__":
    main()
