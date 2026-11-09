from app.core.security import create_access_token, hash_password
from app.models import User, Conversation


def _authenticated_user(db_session):
    user = User(
        email="conversation-create@example.com",
        name="Conversation Test",
        password_hash=hash_password("password123"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    token = create_access_token(subject=str(user.id))
    return user, {"Authorization": f"Bearer {token}"}


def test_create_conversation_matches_frontend_request(client, db_session):
    user, headers = _authenticated_user(db_session)
    response = client.post(
        "/api/conversations",
        headers=headers,
        json={"title": "New Chat"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == user.id
    assert body["title"] == "New Chat"

    listing = client.get("/api/conversations", headers=headers)
    assert listing.status_code == 200
    assert any(item["id"] == body["id"] for item in listing.json())
