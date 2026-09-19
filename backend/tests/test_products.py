import pytest

pytestmark = pytest.mark.asyncio


async def _signed_up_token(client, email: str) -> str:
    r = await client.post("/auth/signup", json={"email": email, "password": "whatever123"})
    return r.json()["access_token"]


async def test_product_crud(client):
    token = await _signed_up_token(client, "test-dana@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.get("/products", headers=headers)
    assert r.status_code == 200
    assert r.json() == []

    r = await client.post(
        "/products", headers=headers,
        json={"name": "Ябълки", "category": "Плодове", "unit": "кг", "price": 2.5, "stock": 100},
    )
    assert r.status_code == 201
    created = r.json()
    assert created["name"] == "Ябълки"
    assert created["price"] == 2.5
    assert created["stock"] == 100
    product_id = created["id"]

    r = await client.get("/products", headers=headers)
    assert [p["id"] for p in r.json()] == [product_id]

    r = await client.put(
        f"/products/{product_id}", headers=headers,
        json={"name": "Ябълки", "category": "Плодове", "unit": "кг", "price": 3.0, "stock": 90},
    )
    assert r.status_code == 200
    assert r.json()["price"] == 3.0
    assert r.json()["stock"] == 90

    r = await client.delete(f"/products/{product_id}", headers=headers)
    assert r.status_code == 204

    r = await client.get("/products", headers=headers)
    assert r.json() == []


async def test_products_require_auth(client):
    r = await client.get("/products")
    assert r.status_code == 401
    r = await client.post("/products", json={"name": "x"})
    assert r.status_code == 401


async def test_products_are_isolated_per_owner(client):
    token_a = await _signed_up_token(client, "test-erin@example.com")
    token_b = await _signed_up_token(client, "test-frank@example.com")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    r = await client.post("/products", headers=headers_a, json={"name": "Erin's product"})
    product_id = r.json()["id"]

    # B can't see A's product in their list...
    r = await client.get("/products", headers=headers_b)
    assert r.json() == []

    # ...can't update it...
    r = await client.put(
        f"/products/{product_id}", headers=headers_b, json={"name": "hijacked"}
    )
    assert r.status_code == 404

    # ...and can't delete it.
    r = await client.delete(f"/products/{product_id}", headers=headers_b)
    assert r.status_code == 404

    # It's still there for A, untouched.
    r = await client.get("/products", headers=headers_a)
    assert len(r.json()) == 1
    assert r.json()[0]["name"] == "Erin's product"
