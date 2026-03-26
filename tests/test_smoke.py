# Smoke checks for the character endpoint.
# These verify that the API is reachable and returns expected structure —
# no game state changes happen here.


def test_get_character_returns_200(client, character_name):
    """Public GET /characters/{name} should return 200 for a known character."""
    response = client.get(f"/characters/{character_name}")
    assert response.status_code == 200


def test_get_character_has_required_fields(client, character_name):
    """Character response must include the fields used in all downstream scenarios."""
    data = client.get(f"/characters/{character_name}").json()["data"]
    for field in ("name", "level", "x", "y", "hp"):
        assert field in data, f"Missing field: {field}"


def test_get_unknown_character_returns_404(client):
    """Requesting a non-existent character should return 404, not a server error."""
    response = client.get("/characters/this_character_does_not_exist_xyz")
    assert response.status_code == 404


# --- Movement ---

def test_move_endpoint_reachable(client, character_name):
    """
    POST /my/{name}/action/move must respond with a known game code.
    Does not assert on 200 — cooldown and position state vary between runs.
    """
    response = client.post(f"/my/{character_name}/action/move", json={"x": 0, "y": 1})
    assert response.status_code in (200, 490, 499), (
        f"unexpected status from move endpoint: {response.status_code}"
    )


# --- Bank ---

def test_bank_items_endpoint_reachable(client):
    """GET /my/bank/items must return 200 with a data envelope for an authenticated account."""
    response = client.get("/my/bank/items")
    assert response.status_code == 200
    assert "data" in response.json()


# --- Combat ---

def test_fight_endpoint_reachable(client, character_name):
    """POST /my/{name}/action/fight must respond with a known game code."""
    response = client.post(f"/my/{character_name}/action/fight")
    assert response.status_code in (200, 499), (
        f"unexpected status from fight endpoint: {response.status_code}"
    )


# --- Rest ---

def test_rest_endpoint_reachable(client, character_name):
    """POST /my/{name}/action/rest must respond with a known game code."""
    response = client.post(f"/my/{character_name}/action/rest")
    assert response.status_code in (200, 499), (
        f"unexpected status from rest endpoint: {response.status_code}"
    )


# --- Gathering ---

def test_gather_endpoint_reachable(client, character_name):
    """
    POST /my/{name}/action/gathering must respond with a known game code.
    Does not assert on 200 — resource tile, cooldown, and inventory state vary between runs.
    """
    response = client.post(f"/my/{character_name}/action/gathering")
    assert response.status_code in (200, 497, 499, 598), (
        f"unexpected status from gather endpoint: {response.status_code}"
    )


# --- Crafting ---

def test_craft_endpoint_reachable(client, character_name):
    """
    POST /my/{name}/action/crafting must respond with a known game code.
    Does not assert on 200 — requires correct workshop tile, materials, and skill level.
    493 = skill too low, 478 = missing items, 598 = not on a workshop tile.
    """
    response = client.post(
        f"/my/{character_name}/action/crafting",
        json={"code": "copper_bar", "quantity": 1},
    )
    assert response.status_code in (200, 478, 493, 499, 598), (
        f"unexpected status from crafting endpoint: {response.status_code}"
    )


# --- Tasks ---

def test_task_state_readable_from_character(client, character_name):
    """
    Task state lives on the character object, not on a separate endpoint.
    GET /characters/{name} must include all task fields needed by get_task_state.
    """
    data = client.get(f"/characters/{character_name}").json()["data"]
    for field in ("task", "task_type", "task_progress", "task_total"):
        assert field in data, f"character response missing task field: {field!r}"


def test_task_accept_endpoint_reachable(client, character_name):
    """
    POST /my/{name}/action/task/new must respond with a known game code.
    489 = character already has a task, 499 = on cooldown, 598 = not on taskmaster tile.
    """
    response = client.post(f"/my/{character_name}/action/task/new")
    assert response.status_code in (200, 489, 499, 598), (
        f"unexpected status from task/new endpoint: {response.status_code}"
    )


# --- Maps ---

def test_maps_endpoint_reachable(client):
    """
    GET /maps must return 200 with a paginated data envelope.
    This is a public endpoint — no auth needed, but client is authenticated anyway.
    Verifies the map data source used by the map cache is reachable.
    """
    response = client.get("/maps", params={"page": 1, "size": 1})
    assert response.status_code == 200, (
        f"unexpected status from /maps endpoint: {response.status_code}"
    )
    body = response.json()
    assert "data" in body
    assert "total" in body
    assert body["total"] > 0, "maps endpoint returned 0 tiles"
