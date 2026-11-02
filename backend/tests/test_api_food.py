from app.core.security import hash_password
from app.models import User


def _setup_user_and_token(client, db, email="food@example.com"):
    user = User(email=email, name="Test", password_hash=hash_password("password123"))
    db.add(user)
    db.commit()
    db.refresh(user)
    res = client.post("/api/auth/login", json={"email": email, "password": "password123"})
    return user, res.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_food_search_returns_external_links(client):
    res = client.post("/api/food/search", json={
        "location": "Bhopal",
        "preference": "vegetarian",
        "budget": "under 500"
    })
    assert res.status_code == 200
    data = res.json()
    assert "Live restaurant discovery is not configured" in data["disclaimer"]
    assert "Google Maps" in data["external_links"]
    assert "Zomato" in data["external_links"]
    # Verify URL encoding in query
    assert "Bhopal" in data["external_links"]["Google Maps"]
    assert "vegetarian" in data["external_links"]["Google Maps"]


def test_favorites(client, db_session):
    user, token = _setup_user_and_token(client, db_session)
    
    # Create favorite
    res = client.post("/api/food/favorites", headers=_auth(token), json={
        "name": "Cafe Terrasse",
        "location": "Bhopal",
        "notes": "Great coffee"
    })
    assert res.status_code == 201
    fav_id = res.json()["id"]

    # List favorites
    res = client.get("/api/food/favorites", headers=_auth(token))
    assert len(res.json()) == 1
    assert res.json()[0]["name"] == "Cafe Terrasse"

    # Delete favorite
    res = client.delete(f"/api/food/favorites/{fav_id}", headers=_auth(token))
    assert res.status_code == 204

    res = client.get("/api/food/favorites", headers=_auth(token))
    assert len(res.json()) == 0