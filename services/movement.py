# Movement helpers for Artifacts MMO.
# Position is part of character state — we read it via GET /characters/{name},
# not from the action response, so it's always fresh from the server.

from services.errors import ALREADY_AT_DESTINATION


def get_position(client, character_name: str) -> dict:
    """
    Return the current map position of the character as {"x": int, "y": int}.
    Uses the public character endpoint — no auth required, always up-to-date.
    """
    response = client.get(f"/characters/{character_name}")
    response.raise_for_status()
    data = response.json()["data"]
    return {"x": data["x"], "y": data["y"]}


def move_character(client, character_name: str, x: int, y: int):
    """
    Send the move action to the given coordinates.
    Returns the raw response — callers decide how to handle 490/499.
    """
    return client.post(f"/my/{character_name}/action/move", json={"x": x, "y": y})


def is_already_at_destination(response) -> bool:
    """
    Return True if the API rejected the move because the character is already there.
    490 is a valid game state, not an error — character is exactly where we wanted.
    """
    return response.status_code == ALREADY_AT_DESTINATION
