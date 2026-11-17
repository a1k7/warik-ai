from app.core.security import hash_password
from app.models import User


def setup(client, db, email="ledger@example.com"):
    user = User(email=email, name="Test", password_hash=hash_password("password123"))
    db.add(user)
    db.commit()
    db.refresh(user)
    response = client.post("/api/auth/login", json={"email": email, "password": "password123"})
    return user, {"Authorization": "Bearer " + response.json()["access_token"]}


def test_commitment_requires_verification_before_completion(client, db_session):
    _, headers = setup(client, db_session)
    created = client.post(
        "/api/commitments/", headers=headers,
        json={"title": "Get project feedback", "counterparty": "Rahul"},
    )
    assert created.status_code == 201
    item_id = created.json()["id"]

    rejected = client.patch(
        f"/api/commitments/{item_id}", headers=headers,
        json={"status": "completed"},
    )
    assert rejected.status_code == 422
    assert "verification note" in rejected.json()["detail"].lower()

    completed = client.patch(
        f"/api/commitments/{item_id}", headers=headers,
        json={"status": "completed", "verification_note": "Feedback received in email"},
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    assert completed.json()["verified_at"] is not None
    assert completed.json()["verification_note"] == "Feedback received in email"


def test_commitments_are_private_to_their_owner(client, db_session):
    _, headers1 = setup(client, db_session, "ledger-one@example.com")
    _, headers2 = setup(client, db_session, "ledger-two@example.com")
    created = client.post(
        "/api/commitments/", headers=headers1,
        json={"title": "Private commitment"},
    )
    item_id = created.json()["id"]

    assert client.get("/api/commitments/", headers=headers2).json() == []
    assert client.patch(
        f"/api/commitments/{item_id}", headers=headers2,
        json={"status": "in_progress"},
    ).status_code == 404
    assert client.delete(f"/api/commitments/{item_id}", headers=headers2).status_code == 404


def test_commitment_status_filter(client, db_session):
    _, headers = setup(client, db_session)
    client.post("/api/commitments/", headers=headers, json={"title": "Open item"})
    waiting = client.post("/api/commitments/", headers=headers, json={"title": "Waiting item"})
    client.patch(
        f"/api/commitments/{waiting.json()['id']}", headers=headers,
        json={"status": "waiting"},
    )
    response = client.get("/api/commitments/?status=waiting", headers=headers)
    assert len(response.json()) == 1
    assert response.json()[0]["title"] == "Waiting item"
