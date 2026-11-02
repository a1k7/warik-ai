def _register(client, email: str, name: str = "Test", password: str = "password123"):
    return client.post(
        "/api/auth/register",
        json={"email": email, "name": name, "password": password},
    )


def test_register_and_me(client):
    response = _register(client, "founder@example.com", "Akhilesh")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["user"]["email"] == "founder@example.com"
    assert body["access_token"]
    assert body["token_type"] == "bearer"

    token = body["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["name"] == "Akhilesh"


def test_duplicate_email_rejected(client):
    payload = {"email": "dup@example.com", "name": "X", "password": "password123"}
    first = client.post("/api/auth/register", json=payload)
    assert first.status_code == 201

    second = client.post("/api/auth/register", json=payload)
    assert second.status_code == 409


def test_login_wrong_password(client):
    _register(client, "user@example.com", password="correctpass123")
    response = client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "wrongpass123"},
    )
    assert response.status_code == 401


def test_login_success(client):
    _register(client, "login@example.com", password="correctpass123")
    response = client.post(
        "/api/auth/login",
        json={"email": "login@example.com", "password": "correctpass123"},
    )
    assert response.status_code == 200
    assert response.json()["access_token"]


def test_protected_route_without_token(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_protected_route_with_garbage_token(client):
    response = client.get(
        "/api/auth/me",
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert response.status_code == 401