def test_get_character_returns_200(client, character_name):
    response = client.get(f"/characters/{character_name}")
    assert response.status_code == 200


def test_get_character_has_required_fields(client, character_name):
    data = client.get(f"/characters/{character_name}").json()["data"]
    for field in ("name", "level", "x", "y", "hp"):
        assert field in data, f"Missing field: {field}"


def test_get_unknown_character_returns_404(client):
    response = client.get("/characters/this_character_does_not_exist_xyz")
    assert response.status_code == 404
