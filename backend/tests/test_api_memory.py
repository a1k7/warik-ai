from app.core.security import hash_password
from app.models import Memory, User


def _setup_user_and_token(client, db, email="mem@example.com"):
    user = User(email=email, name="Test", password_hash=hash_password("password123"))
    db.add(user)
    db.commit()
    db.refresh(user)
    res = client.post("/api/auth/login", json={"email": email, "password": "password123"})
    return user, res.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_create_list_update_delete_memory(client, db_session):
    user, token = _setup_user_and_token(client, db_session)
    
    # Create
    res = client.post("/api/memories/", headers=_auth(token), json={"content": "I prefer train travel"})
    assert res.status_code == 201
    mem_id = res.json()["id"]

    # List
    res = client.get("/api/memories/", headers=_auth(token))
    assert len(res.json()) == 1
    assert res.json()[0]["content"] == "I prefer train travel"

    # Update
    res = client.put(f"/api/memories/{mem_id}", headers=_auth(token), json={"content": "I prefer flights"})
    assert res.status_code == 200
    assert res.json()["content"] == "I prefer flights"

    # Delete
    res = client.delete(f"/api/memories/{mem_id}", headers=_auth(token))
    assert res.status_code == 204

    res = client.get("/api/memories/", headers=_auth(token))
    assert len(res.json()) == 0


def test_delete_all_memories(client, db_session):
    user, token = _setup_user_and_token(client, db_session)
    
    client.post("/api/memories/", headers=_auth(token), json={"content": "Fact 1"})
    client.post("/api/memories/", headers=_auth(token), json={"content": "Fact 2"})

    res = client.get("/api/memories/", headers=_auth(token))
    assert len(res.json()) == 2

    res = client.delete("/api/memories/", headers=_auth(token))
    assert res.status_code == 204

    res = client.get("/api/memories/", headers=_auth(token))
    assert len(res.json()) == 0