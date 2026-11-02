from datetime import datetime, timedelta, timezone

from app.core.security import hash_password
from app.models import Task, User


def _setup_user_and_token(client, db, email="tasks@example.com"):
    user = User(email=email, name="Test", password_hash=hash_password("password123"))
    db.add(user)
    db.commit()
    db.refresh(user)

    res = client.post("/api/auth/login", json={"email": email, "password": "password123"})
    return user, res.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_create_task(client, db_session):
    user, token = _setup_user_and_token(client, db_session)
    payload = {"title": "Test task", "priority": "high"}

    res = client.post("/api/tasks/", headers=_auth(token), json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["title"] == "Test task"
    assert data["priority"] == "high"
    assert data["completed"] is False
    assert data["user_id"] == user.id


def test_list_tasks_filtering(client, db_session):
    user, token = _setup_user_and_token(client, db_session)
    
    # Create two tasks
    client.post("/api/tasks/", headers=_auth(token), json={"title": "Task 1"})
    res2 = client.post("/api/tasks/", headers=_auth(token), json={"title": "Task 2"})
    task2_id = res2.json()["id"]
    
    # Complete task 2
    client.post(f"/api/tasks/{task2_id}/complete", headers=_auth(token))

    # Fetch all
    res = client.get("/api/tasks/", headers=_auth(token))
    assert len(res.json()) == 2

    # Fetch incomplete
    res = client.get("/api/tasks/?completed=false", headers=_auth(token))
    assert len(res.json()) == 1
    assert res.json()[0]["title"] == "Task 1"

    # Fetch completed
    res = client.get("/api/tasks/?completed=true", headers=_auth(token))
    assert len(res.json()) == 1
    assert res.json()[0]["title"] == "Task 2"


def test_update_and_delete_task(client, db_session):
    user, token = _setup_user_and_token(client, db_session)
    res = client.post("/api/tasks/", headers=_auth(token), json={"title": "Original"})
    task_id = res.json()["id"]

    res = client.put(f"/api/tasks/{task_id}", headers=_auth(token), json={"title": "Updated"})
    assert res.status_code == 200
    assert res.json()["title"] == "Updated"

    res = client.delete(f"/api/tasks/{task_id}", headers=_auth(token))
    assert res.status_code == 204

    # Fetch all (omitting the filter defaults to all tasks, which should now be 0)
    res = client.get("/api/tasks/", headers=_auth(token))
    assert len(res.json()) == 0


def test_user_cannot_see_other_tasks(client, db_session):
    user1, token1 = _setup_user_and_token(client, db_session, "u1@example.com")
    user2, token2 = _setup_user_and_token(client, db_session, "u2@example.com")

    # User 1 creates a task
    client.post("/api/tasks/", headers=_auth(token1), json={"title": "Secret task"})

    # User 2 tries to list
    res = client.get("/api/tasks/", headers=_auth(token2))
    assert len(res.json()) == 0