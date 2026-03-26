# Rest tests for Artifacts MMO.
# Rest is a POST action — it restores HP and triggers a cooldown.
# No location requirement — rest works anywhere on the map.
# All stateful tests call wait_for_cooldown before acting.

import logging

from services.cooldown import wait_for_cooldown, parse_cooldown
from services.movement import move_character
from services.rest import rest, get_hp, is_full_hp

logger = logging.getLogger(__name__)

# Chicken at (0, 1) — level 1 monster, safe for damage setup before rest tests.
MONSTER_TILE = (0, 1)


def test_rest_returns_200(client, character_name):
    """
    Rest must return 200. No location required.
    """
    wait_for_cooldown(client, character_name)
    response = rest(client, character_name)

    assert response.status_code == 200, (
        f"expected 200 from rest, got {response.status_code}: {response.text}"
    )
    logger.info("rest: status=200")


def test_rest_has_cooldown_in_response(client, character_name):
    """
    A successful rest must include cooldown data in the response body.
    Cooldown is mandatory after every action in Artifacts MMO.
    """
    wait_for_cooldown(client, character_name)
    response = rest(client, character_name)

    assert response.status_code == 200, (
        f"expected 200 to check cooldown, got {response.status_code}: {response.text}"
    )

    cooldown = parse_cooldown(response)
    assert cooldown is not None, "rest response must include cooldown data"
    assert "remaining_seconds" in cooldown, "cooldown must include remaining_seconds"

    logger.info(
        "rest cooldown: remaining=%.1fs total=%ds",
        cooldown.get("remaining_seconds", 0),
        cooldown.get("total_time", 0),
    )


def test_rest_hp_readable_before_and_after(client, character_name):
    """
    HP must be readable before and after rest, and must not decrease as a result.
    At full HP, rest succeeds but HP stays the same — that is a valid outcome.
    """
    wait_for_cooldown(client, character_name)
    hp_before, max_hp = get_hp(client, character_name)
    logger.info("HP before rest: %d / %d", hp_before, max_hp)

    response = rest(client, character_name)
    assert response.status_code == 200, (
        f"expected 200 from rest, got {response.status_code}: {response.text}"
    )

    hp_after, _ = get_hp(client, character_name)
    logger.info("HP after rest: %d / %d", hp_after, max_hp)

    assert hp_after >= hp_before, (
        f"HP must not decrease after rest: before={hp_before} after={hp_after}"
    )


def test_rest_restores_hp_after_combat(client, character_name):
    """
    After taking damage in a fight, rest must restore at least some HP.
    Flow: move to monster tile → fight → if damaged → rest → assert HP increased.
    If the fight deals no damage (character too strong), we log and skip the HP assertion.
    """
    wait_for_cooldown(client, character_name)
    move_character(client, character_name, *MONSTER_TILE)

    wait_for_cooldown(client, character_name)
    hp_before_fight, max_hp = get_hp(client, character_name)

    fight_response = client.post(f"/my/{character_name}/action/fight")
    assert fight_response.status_code == 200, (
        f"expected 200 from fight, got {fight_response.status_code}: {fight_response.text}"
    )

    wait_for_cooldown(client, character_name)
    hp_after_fight, _ = get_hp(client, character_name)
    logger.info("HP: before fight=%d, after fight=%d / %d", hp_before_fight, hp_after_fight, max_hp)

    if hp_after_fight >= hp_before_fight:
        logger.info("no damage taken in fight — skipping HP recovery assertion")
        return

    damage_taken = hp_before_fight - hp_after_fight
    logger.info("damage taken: %d — now resting", damage_taken)

    rest_response = rest(client, character_name)
    assert rest_response.status_code == 200, (
        f"expected 200 from rest, got {rest_response.status_code}: {rest_response.text}"
    )

    wait_for_cooldown(client, character_name)
    hp_after_rest, _ = get_hp(client, character_name)
    logger.info("HP after rest: %d / %d", hp_after_rest, max_hp)

    assert hp_after_rest > hp_after_fight, (
        f"rest must restore HP after damage: after_fight={hp_after_fight} after_rest={hp_after_rest}"
    )
    logger.info("HP restored: %d → %d (+%d)", hp_after_fight, hp_after_rest, hp_after_rest - hp_after_fight)
