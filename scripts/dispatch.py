#!/usr/bin/env python
"""
Dispatch loop runner for Artifacts MMO.

Usage:
    python scripts/dispatch.py              # run forever
    python scripts/dispatch.py --cycles 3  # run 3 dispatch iterations and stop

Roles are defined in services/scenario.py → ROLES dict.
Resource tile TODOs (woodcutting, alchemy) are logged as warnings and skipped
until task 18.1 (map discovery) fills them in.
"""

import argparse
import logging
import os
import sys

# Allow running from project root: python scripts/dispatch.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from clients.artifacts_client import ArtifactsClient
from services.scenario import run_dispatch_loop, ROLES

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("dispatch")


def main():
    parser = argparse.ArgumentParser(description="Artifacts MMO dispatch loop")
    parser.add_argument(
        "--cycles",
        type=int,
        default=None,
        help="number of dispatch iterations before stopping (default: run forever)",
    )
    args = parser.parse_args()

    token = os.getenv("ARTIFACTS_TOKEN")
    if not token:
        logger.error("ARTIFACTS_TOKEN not set in .env")
        sys.exit(1)

    client = ArtifactsClient(token)

    logger.info("starting dispatch | roles: %s", ROLES)
    if args.cycles:
        logger.info("will stop after %d cycle(s)", args.cycles)

    try:
        run_dispatch_loop(client, max_cycles=args.cycles)
    except KeyboardInterrupt:
        logger.info("dispatch stopped by user")


if __name__ == "__main__":
    main()
