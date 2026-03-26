# Gathering helpers for Artifacts MMO.
# Gathering is a stateful action — it consumes a cooldown slot and modifies inventory.
# The character must be on a map tile with a gatherable resource for 200 to occur.


def gather(client, character_name: str):
    """
    Send the gathering action at the character's current location.
    Returns the raw response — callers handle 200/497/499 based on context.
    No body needed; the server determines what resource is at the current tile.
    """
    return client.post(f"/my/{character_name}/action/gathering")


def parse_gathered_items(response) -> list:
    """
    Extract the list of items collected from a successful gather response.
    Artifacts returns items under data.details.items as [{"code": str, "quantity": int}].
    Returns an empty list if the response has no items (e.g. cooldown or error responses).
    """
    try:
        return response.json()["data"]["details"]["items"]
    except (KeyError, TypeError, ValueError):
        return []
