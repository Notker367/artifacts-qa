#!/usr/bin/env python3
"""
Search map tile coordinates by content code.

Given one or more content codes (resource, monster, building), prints all tiles
that contain that content. With no codes and no flags, prints all resource tiles
grouped by gathering role.

Usage:
    python scripts/discover_map.py                     # all resource tiles by role
    python scripts/discover_map.py ash_tree            # where is ash_tree?
    python scripts/discover_map.py chicken bank        # multiple codes
    python scripts/discover_map.py --all               # all content types
    python scripts/discover_map.py --refresh           # force fresh fetch from API
    python scripts/discover_map.py --refresh ash_tree  # refresh then search
"""

import os
import sys
import argparse
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from clients.artifacts_client import ArtifactsClient
from services.map_cache import get_map_cache, find_content, find_tiles, CACHE_FILE

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Default view: resource codes grouped by gathering role
ROLE_RESOURCES = {
    "mining":      ["copper_rocks", "iron_rocks", "coal_rocks", "gold_rocks", "mithril_rocks", "adamantite_rocks"],
    "woodcutting": ["ash_tree", "birch_tree", "spruce_tree", "maple_tree", "dead_tree", "palm_tree"],
    "fishing":     ["gudgeon_spot", "shrimp_spot", "salmon_spot", "trout_spot", "bass_spot", "swordfish_spot"],
    "alchemy":     ["sunflower_field", "glowstem", "nettle", "torch_cactus"],
}

# Content types included in --all output
ALL_CONTENT_TYPES = ["resource", "monster", "workshop", "bank", "tasks_master", "grand_exchange"]


def _fmt_tile(tile: dict) -> str:
    layer = f" [{tile['layer']}]" if tile.get("layer") == "underground" else ""
    return f"({tile['x']}, {tile['y']}){layer}"


def search_codes(cache: dict, codes: list) -> None:
    """Print tile coordinates for each requested content code."""
    for code in codes:
        matches = find_content(cache, code)
        if matches:
            coords = "  ".join(_fmt_tile(t) for t in matches)
            ctype = matches[0].get("content_type", "?")
            print(f"  {code:<24} [{ctype}]  {coords}")
        else:
            print(f"  {code:<24} not found in cache")


def print_resources_by_role(cache: dict) -> None:
    """Default view: resource tiles grouped by gathering role."""
    for role, codes in ROLE_RESOURCES.items():
        print(f"\n=== {role} ===")
        for code in codes:
            matches = find_content(cache, code)
            if matches:
                coords = "  ".join(_fmt_tile(t) for t in matches)
                print(f"  {code:<24} {coords}")


def print_all_content_types(cache: dict) -> None:
    """Extended view: every content type with all tiles."""
    for ctype in ALL_CONTENT_TYPES:
        tiles = find_tiles(cache, ctype)
        if not tiles:
            continue
        print(f"\n=== {ctype} ({len(tiles)} tiles) ===")
        for t in sorted(tiles, key=lambda x: x.get("content_code", "")):
            print(f"  {_fmt_tile(t):<20}  {t.get('content_code', '')}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Search map tile coordinates by content code")
    parser.add_argument("codes", nargs="*", help="Content codes to search (e.g. ash_tree chicken bank)")
    parser.add_argument("--refresh", action="store_true", help="Force fresh fetch from API")
    parser.add_argument("--all", action="store_true", help="Show all content types (resource/monster/workshop/...)")
    args = parser.parse_args()

    token = os.getenv("ARTIFACTS_TOKEN")
    if not token:
        print("ERROR: ARTIFACTS_TOKEN env var not set")
        sys.exit(1)
    client = ArtifactsClient(token)

    if not args.refresh and CACHE_FILE.exists():
        print(f"[cache] {CACHE_FILE}")
    else:
        print("[cache] fetching all map tiles from API (~15 requests)...")

    cache = get_map_cache(client, force=args.refresh)
    tile_count = len(cache.get("tiles", []))
    print(f"[cache] {tile_count} tiles | fetched_at: {cache.get('fetched_at', '?')}\n")

    if args.codes:
        # Search mode: look up each provided code
        search_codes(cache, args.codes)
    elif args.all:
        print_all_content_types(cache)
    else:
        print_resources_by_role(cache)

    print()


if __name__ == "__main__":
    main()
