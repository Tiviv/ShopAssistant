import pytest

pytestmark = pytest.mark.asyncio


async def _signed_up_token(client, email: str) -> str:
    r = await client.post("/auth/signup", json={"email": email, "password": "whatever123"})
    return r.json()["access_token"]


async def test_customer_crud(client):
    token = await _signed_up_token(client, "test-gina@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.get("/customers", headers=headers)
    assert r.status_code == 200
    assert r.json() == []

    r = await client.post(
        "/customers", headers=headers,
        json={"name": "Иван Иванов", "eik": "123456789", "vat_number": "BG123456789",
              "address": "ул. Тест 1", "phone": "0888123456", "email": "ivan@example.com"},
    )
    assert r.status_code == 201
    created = r.json()
    assert created["name"] == "Иван Иванов"
    assert created["vat_number"] == "BG123456789"
    customer_id = created["id"]

    r = await client.get("/customers", headers=headers)
    assert [c["id"] for c in r.json()] == [customer_id]

    r = await client.put(
        f"/customers/{customer_id}", headers=headers,
        json={"name": "Иван Петров", "eik": "123456789", "vat_number": "BG123456789",
              "address": "ул. Тест 2", "phone": "0888123456", "email": "ivan@example.com"},
    )
    assert r.status_code == 200
    assert r.json()["name"] == "Иван Петров"
    assert r.json()["address"] == "ул. Тест 2"

    r = await client.delete(f"/customers/{customer_id}", headers=headers)
    assert r.status_code == 204

    r = await client.get("/customers", headers=headers)
    assert r.json() == []


async def test_customer_defaults_blank_fields(client):
    token = await _signed_up_token(client, "test-henry@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.post("/customers", headers=headers, json={"name": "Just a name"})
    assert r.status_code == 201
    body = r.json()
    assert body["eik"] == "" and body["vat_number"] == "" and body["phone"] == "" and body["email"] == ""


async def test_customers_require_auth(client):
    r = await client.get("/customers")
    assert r.status_code == 401
    r = await client.post("/customers", json={"name": "x"})
    assert r.status_code == 401


async def test_customers_are_isolated_per_owner(client):
    token_a = await _signed_up_token(client, "test-ivy@example.com")
    token_b = await _signed_up_token(client, "test-jack@example.com")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    r = await client.post("/customers", headers=headers_a, json={"name": "Ivy's customer"})
    customer_id = r.json()["id"]

    r = await client.get("/customers", headers=headers_b)
    assert r.json() == []

    r = await client.put(f"/customers/{customer_id}", headers=headers_b, json={"name": "hijacked"})
    assert r.status_code == 404

    r = await client.delete(f"/customers/{customer_id}", headers=headers_b)
    assert r.status_code == 404

    r = await client.get("/customers", headers=headers_a)
    assert len(r.json()) == 1
    assert r.json()[0]["name"] == "Ivy's customer"
