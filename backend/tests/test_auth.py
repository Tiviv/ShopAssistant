import pytest

pytestmark = pytest.mark.asyncio


async def test_signup_login_and_me(client):
    email = "test-alice@example.com"
    password = "correct horse battery staple"

    r = await client.post("/auth/signup", json={"email": email, "password": password})
    assert r.status_code == 201
    token = r.json()["access_token"]

    r = await client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    assert r.json()["access_token"]

    r = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == email


async def test_login_wrong_password_rejected(client):
    email = "test-bob@example.com"
    await client.post("/auth/signup", json={"email": email, "password": "correct-password"})

    r = await client.post("/auth/login", json={"email": email, "password": "wrong-password"})
    assert r.status_code == 401


async def test_me_without_token_rejected(client):
    r = await client.get("/auth/me")
    assert r.status_code == 401


async def test_duplicate_signup_rejected(client):
    email = "test-carol@example.com"
    await client.post("/auth/signup", json={"email": email, "password": "whatever123"})

    r = await client.post("/auth/signup", json={"email": email, "password": "whatever123"})
    assert r.status_code == 400
