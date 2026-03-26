#!/usr/bin/env python3
"""
Farm runner for Artifacts MMO.

Configures each character, runs a startup phase, then launches the dispatch loop.

Startup phase (once per run, in character order):
  1. wait for cooldown to expire
  2. rest if HP is below 50% (avoid entering a fight half-dead)
  3. if combat role and no task: move to taskmaster → accept monster task

After startup the dispatch loop runs indefinitely (or --cycles N iterations):
  - combat chars: fight chicken → rest if low HP → complete/re-accept task
  - gathering chars: deposit if inventory low → move to resource → gather

Current farm config — update roles and resources as characters level up:

  Furiba      combat      chicken / (0,1)        task: monster task
  Fussat      fishing     gudgeon_spot / (4,2)   no rod yet → may get 598
  Velikossat  woodcutting ash_tree / (-1,0)      no tool yet → may get 598
  Ognerot     mining      copper_rocks / (2,0)   no tool yet → may get 598
  Mikrochelo  alchemy     sunflower_field / (2,2) no tool yet → may get 598

Usage:
    python scripts/farm.py              # run forever
    python scripts/farm.py --cycles 5  # run 5 dispatch iterations then stop
"""

import argparse
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from clients.artifacts_client import ArtifactsClient
from services.cooldown import wait_for_cooldown
from services.movement import move_character
from services.rest import get_hp, rest
from services.tasks import get_task_state, has_active_task, accept_task
from services.scenario import run_dispatch_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("farm")

# ---------------------------------------------------------------------------
# Farm configuration
# ---------------------------------------------------------------------------

# Role per character. Change one line to reassign.
FARM_ROLES = {
    "Furiba":     "combat",
    "Fussat":     "fishing",
    "Velikossat": "woodcutting",
    "Ognerot":    "mining",
    "Mikrochelo": "alchemy",
}

# Combat characters accept tasks from this taskmaster tile.
MONSTERS_TASKMASTER_TILE = (1, 2)

# Rest before starting if HP is below this fraction (50%).
# Higher than the in-loop threshold (30%) to start each session healthy.
STARTUP_HP_THRESHOLD = 0.5


# ---------------------------------------------------------------------------
# Startup helpers
# ---------------------------------------------------------------------------

def _startup_rest(client, name: str) -> None:
    """Rest if HP is below STARTUP_HP_THRESHOLD. Skips if already healthy."""
    hp, max_hp = get_hp(client, name)
    if max_hp == 0:
        return
    ratio = hp / max_hp
    if ratio >= STARTUP_HP_THRESHOLD:
        logger.info("%s: HP %.0f%% — OK, no rest needed", name, ratio * 100)
        return
    logger.info("%s: HP %.0f%% — resting before farm starts", name, ratio * 100)
    wait_for_cooldown(client, name)
    rest(client, name)
    hp, max_hp = get_hp(client, name)
    logger.info("%s: HP after rest: %d/%d", name, hp, max_hp)


def _startup_accept_task(client, name: str) -> None:
    """
    Ensure a combat character has an active task.
    If no task: move to taskmaster and accept one.
    If already has a task: skip (preserve existing progress).
    """
    state = get_task_state(client, name)
    if has_active_task(state):
        logger.info(
            "%s: task already active — %s %d/%d",
            name, state["task"], state["task_progress"], state["task_total"],
        )
        return

    logger.info("%s: no task — moving to taskmaster at %s", name, MONSTERS_TASKMASTER_TILE)
    wait_for_cooldown(client, name)
    move_character(client, name, *MONSTERS_TASKMASTER_TILE)

    wait_for_cooldown(client, name)
    response = accept_task(client, name)
    if response.status_code == 200:
        state = get_task_state(client, name)
        logger.info(
            "%s: task accepted — %s × %d",
            name, state["task"], state["task_total"],
        )
    else:
        logger.warning("%s: accept_task returned %d — continuing anyway", name, response.status_code)


def run_startup(client: ArtifactsClient) -> None:
    """
    Run the startup phase for all farm characters.
    Processes characters sequentially — cooldowns of earlier chars
    run in the background while we set up the next one.
    """
    logger.info("=== farm startup ===")
    for name, role in FARM_ROLES.items():
        logger.info("--- startup: %s [%s] ---", name, role)
        try:
            wait_for_cooldown(client, name)
            _startup_rest(client, name)

            if role == "combat":
                _startup_accept_task(client, name)
            else:
                logger.info("%s: gathering role — no task needed at startup", name)

        except Exception as exc:
            # One character failing startup must not block the others
            logger.error("%s: startup failed — %s: %s", name, type(exc).__name__, exc)

    logger.info("=== startup complete — launching dispatch loop ===\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Artifacts MMO farm runner")
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

    logger.info("farm config: %s", FARM_ROLES)
    if args.cycles:
        logger.info("will stop after %d dispatch cycle(s)", args.cycles)

    run_startup(client)

    try:
        run_dispatch_loop(client, roles=FARM_ROLES, max_cycles=args.cycles)
    except KeyboardInterrupt:
        logger.info("farm stopped by user (Ctrl+C)")


if __name__ == "__main__":
    main()
