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
