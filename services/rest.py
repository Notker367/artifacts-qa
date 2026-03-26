# Rest helpers for Artifacts MMO.
# Rest is a POST action that restores HP. It triggers a cooldown.
# Used after combat to recover before the next fight.


def rest(client, character_name: str):
    """
    Send the rest action for the character.
    Returns raw response — 200 on success, 499 if on cooldown.
    No location requirement — rest works anywhere.
    """
    return client.post(f"/my/{character_name}/action/rest")


def get_hp(client, character_name: str) -> tuple[int, int]:
    """
    Return (current_hp, max_hp) from character state.
    Used to check whether rest actually restored HP.
    """
    response = client.get(f"/characters/{character_name}")
    response.raise_for_status()
    data = response.json()["data"]
    return data["hp"], data["max_hp"]


def is_full_hp(client, character_name: str) -> bool:
    """Return True if the character is already at full HP."""
    hp, max_hp = get_hp(client, character_name)
    return hp >= max_hp
