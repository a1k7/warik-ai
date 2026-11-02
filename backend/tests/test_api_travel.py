from datetime import date, timedelta
from decimal import Decimal

from app.core.security import hash_password
from app.models import User


def _setup_user_and_token(client, db, email="travel@example.com"):
    user = User(email=email, name="Test", password_hash=hash_password("password123"))
    db.add(user)
    db.commit()
    db.refresh(user)
    res = client.post("/api/auth/login", json={"email": email, "password": "password123"})
    return user, res.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_create_travel_plan(client, db_session):
    user, token = _setup_user_and_token(client, db_session)
    
    today = date.today()
    payload = {
        "title": "Weekend in Indore",
        "origin": "Bhopal",
        "destination": "Indore",
        "start_date": today.isoformat(),
        "end_date": (today + timedelta(days=2)).isoformat(),
        "budget": "2500.00",
        "travellers": 2,
        "stops": [
            {"name": "Bhopal Junction", "arrival": "2026-11-01T08:00:00Z"},
            {"name": "Indore Junction", "arrival": "2026-11-01T12:00:00Z"}
        ]
    }

    res = client.post("/api/travel/", headers=_auth(token), json=payload)
    assert res.status_code == 201, res.text
    data = res.json()
    
    assert data["title"] == "Weekend in Indore"
    assert data["origin"] == "Bhopal"
    assert Decimal(str(data["budget"])) == Decimal("2500.00")
    assert len(data["stops"]) == 2
    assert data["stops"][0]["name"] == "Bhopal Junction"
    assert data["stops"][1]["name"] == "Indore Junction"


def test_list_and_delete_travel_plans(client, db_session):
    user, token = _setup_user_and_token(client, db_session)
    
    payload = {
        "title": "Solo trip",
        "origin": "Delhi",
        "destination": "Jaipur",
        "travellers": 1,
    }
    res = client.post("/api/travel/", headers=_auth(token), json=payload)
    plan_id = res.json()["id"]

    # List
    res = client.get("/api/travel/", headers=_auth(token))
    assert len(res.json()) == 1
    assert res.json()[0]["title"] == "Solo trip"

    # Delete
    res = client.delete(f"/api/travel/{plan_id}", headers=_auth(token))
    assert res.status_code == 204

    # Verify deleted
    res = client.get("/api/travel/", headers=_auth(token))
    assert len(res.json()) == 0