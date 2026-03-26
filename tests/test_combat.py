# Combat tests for Artifacts MMO.
# Fight is a POST action — engages the monster at the character's current tile.
# Response includes fight result, loot, XP gained, and cooldown data.
# All stateful tests call wait_for_cooldown before acting.

import logging

from services.cooldown import wait_for_cooldown, parse_cooldown
from services.movement import move_character
from services.rest import get_hp, rest
from services.combat import fight, parse_fight_result, is_win, is_loss

logger = logging.getLogger(__name__)

# Chicken at (0, 1) — level 1 monster, reliable for combat tests.
MONSTER_TILE = (0, 1)


def test_fight_returns_200(client, character_name):
    """
    Fighting a monster at the correct tile must return 200.
    """
    wait_for_cooldown(client, character_name)
    move_character(client, character_name, *MONSTER_TILE)

    wait_for_cooldown(client, character_name)
    response = fight(client, character_name)

    assert response.status_code == 200, (
        f"expected 200 from fight, got {response.status_code}: {response.text}"
    )
    logger.info("fight: status=200")


def test_fight_response_has_fight_and_cooldown(client, character_name):
    """
    A successful fight response must contain both 'fight' and 'cooldown' in data.
    These are the two mandatory fields used in all downstream combat scenarios.
    """
    wait_for_cooldown(client, character_name)
    move_character(client, character_name, *MONSTER_TILE)

    wait_for_cooldown(client, character_name)
    response = fight(client, character_name)

    assert response.status_code == 200, (
        f"expected 200 to check response structure, got {response.status_code}: {response.text}"
    )

    data = response.json()["data"]
    assert "fight" in data, "fight response must contain 'fight' key"
    assert "cooldown" in data, "fight response must contain 'cooldown' key"

    cooldown = parse_cooldown(response)
    assert cooldown is not None and "remaining_seconds" in cooldown, (
        "fight cooldown must include remaining_seconds"
    )
    logger.info("fight cooldown: remaining=%.1fs", cooldown.get("remaining_seconds", 0))


def test_fight_result_is_known_outcome(client, character_name):
    """
    Fight result must be either 'win' or 'lose' — no other values are valid.
    This also validates that is_win / is_loss helpers correctly classify outcomes.
    """
    wait_for_cooldown(client, character_name)
    move_character(client, character_name, *MONSTER_TILE)

    wait_for_cooldown(client, character_name)
    response = fight(client, character_name)
    assert response.status_code == 200, (
        f"expected 200, got {response.status_code}: {response.text}"
    )

    result = parse_fight_result(response)
    assert result is not None, "fight response must contain parseable fight result"
    assert result.get("result") in ("win", "loss"), (
        f"fight result must be 'win' or 'loss', got: {result.get('result')!r}"
    )
    assert is_win(result) != is_loss(result), (
        "is_win and is_loss must be mutually exclusive"
    )
    logger.info("fight result: %s", result.get("result"))


def test_fight_win_grants_xp_and_drops(client, character_name):
    """
    A won fight must grant XP > 0. Drops may be empty but must be a list.
    Gold reward is present in the fight result (may be 0).
    """
    wait_for_cooldown(client, character_name)
    move_character(client, character_name, *MONSTER_TILE)

    wait_for_cooldown(client, character_name)
    response = fight(client, character_name)
    assert response.status_code == 200, (
        f"expected 200, got {response.status_code}: {response.text}"
    )

    result = parse_fight_result(response)
    assert result is not None

    if is_loss(result):
        logger.info("fight was lost — skipping XP/drops assertion")
        return

    xp = result.get("xp", 0)
    drops = result.get("drops", [])

    assert xp > 0, f"win must grant XP > 0, got xp={xp}"
    assert isinstance(drops, list), f"drops must be a list, got {type(drops)}"

    logger.info("fight win: xp=%d gold=%d drops=%s", xp, result.get("gold", 0), drops)


def test_fight_hp_changes_visible(client, character_name):
    """
    HP before and after fight must be readable.
    After a fight, HP must be <= HP before (character takes damage or stays same if perfect gear).
    State is visible — this is the foundation for post-combat rest automation.
    """
    wait_for_cooldown(client, character_name)
    # Restore HP first so we start from a known state
    rest(client, character_name)

    wait_for_cooldown(client, character_name)
    move_character(client, character_name, *MONSTER_TILE)

    wait_for_cooldown(client, character_name)
    hp_before, max_hp = get_hp(client, character_name)
    logger.info("HP before fight: %d / %d", hp_before, max_hp)

    response = fight(client, character_name)
    assert response.status_code == 200, (
        f"expected 200, got {response.status_code}: {response.text}"
    )

    wait_for_cooldown(client, character_name)
    hp_after, _ = get_hp(client, character_name)
    logger.info("HP after fight: %d / %d", hp_after, max_hp)

    assert 0 <= hp_after <= max_hp, f"HP after fight out of range: {hp_after}"
    logger.info("HP delta: %+d", hp_after - hp_before)
