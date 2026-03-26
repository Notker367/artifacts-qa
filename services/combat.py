# Combat helpers for Artifacts MMO.
# Fight is a POST action — it engages the monster at the character's current tile.
# The response includes the full fight log, loot, XP, and cooldown data.


def fight(client, character_name: str):
    """
    Send the fight action at the character's current location.
    The character must be on a tile with a monster. Returns raw response.
    """
    return client.post(f"/my/{character_name}/action/fight")


def parse_fight_result(response) -> dict | None:
    """
    Extract the fight result block from a successful fight response.
    Returns data.fight dict, or None if not present (e.g. cooldown response).
    Contains: result ("win"/"lose"), xp, gold, drops, turns, logs.
    """
    try:
        return response.json()["data"]["fight"]
    except (KeyError, TypeError, ValueError):
        return None


def is_win(fight_result: dict) -> bool:
    """Return True if the fight was won by the character."""
    return fight_result.get("result") == "win"


def is_loss(fight_result: dict) -> bool:
    """
    Return True if the fight was lost by the character.
    A loss means the character was defeated — HP drops to 0 and recovery is needed.
    API returns "loss", not "lose".
    """
    return fight_result.get("result") == "loss"
