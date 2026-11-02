from decimal import Decimal

from app.core.security import hash_password
from app.models import User


def _setup_user_and_token(client, db, email="exp@example.com"):
    user = User(email=email, name="Test", password_hash=hash_password("password123"))
    db.add(user)
    db.commit()
    db.refresh(user)
    res = client.post("/api/auth/login", json={"email": email, "password": "password123"})
    return user, res.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_create_and_summarize_expense(client, db_session):
    user, token = _setup_user_and_token(client, db_session)
    
    # Set a budget
    client.put("/api/preferences/", headers=_auth(token), json={"monthly_budget": "1000.00"})

    # Create expenses
    client.post("/api/expenses/", headers=_auth(token), json={"amount": "100.50", "category": "Food"})
    client.post("/api/expenses/", headers=_auth(token), json={"amount": "200.00", "category": "Transport"})

    # Summary
    res = client.get("/api/expenses/summary?period=month", headers=_auth(token))
    data = res.json()
    assert Decimal(str(data["total"])) == Decimal("300.50")
    assert len(data["by_category"]) == 2
    assert data["by_category"][0]["category"] == "Transport"
    assert Decimal(str(data["by_category"][0]["amount"])) == Decimal("200.00")

    # Budget status
    res = client.get("/api/expenses/budget-status", headers=_auth(token))
    b_data = res.json()
    assert Decimal(str(b_data["budget"])) == Decimal("1000.00")
    assert Decimal(str(b_data["spent"])) == Decimal("300.50")
    assert b_data["percentage"] == 30.05
    assert b_data["warning"] is False


def test_delete_expense(client, db_session):
    user, token = _setup_user_and_token(client, db_session)
    res = client.post("/api/expenses/", headers=_auth(token), json={"amount": "50.00", "category": "Snacks"})
    exp_id = res.json()["id"]

    res = client.delete(f"/api/expenses/{exp_id}", headers=_auth(token))
    assert res.status_code == 204

    res = client.get("/api/expenses/", headers=_auth(token))
    assert len(res.json()) == 0