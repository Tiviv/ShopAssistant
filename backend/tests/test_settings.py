import pytest

pytestmark = pytest.mark.asyncio


async def _signed_up_token(client, email: str) -> str:
    r = await client.post("/auth/signup", json={"email": email, "password": "whatever123"})
    return r.json()["access_token"]


async def test_settings_created_empty_on_signup(client):
    token = await _signed_up_token(client, "test-una@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.get("/settings", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["company_name"] == ""
    assert body["categories"] == []
    assert body["next_invoice_no"] == 1


async def test_settings_patch_only_touches_given_fields(client):
    token = await _signed_up_token(client, "test-vera@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.patch("/settings", headers=headers, json={"company_name": "Свежо и Вкусно", "eik": "123"})
    assert r.status_code == 200
    assert r.json()["company_name"] == "Свежо и Вкусно"
    assert r.json()["eik"] == "123"

    # A categories-only patch, like the frontend's saveCategories(), must not
    # touch company_name/eik set above.
    r = await client.patch("/settings", headers=headers, json={"categories": ["Плодове", "Зеленчуци"]})
    assert r.status_code == 200
    body = r.json()
    assert body["categories"] == ["Плодове", "Зеленчуци"]
    assert body["company_name"] == "Свежо и Вкусно"
    assert body["eik"] == "123"

    # A counters-only patch, like the frontend's import-restore path.
    r = await client.patch("/settings", headers=headers, json={"next_invoice_no": 42})
    assert r.status_code == 200
    body = r.json()
    assert body["next_invoice_no"] == 42
    assert body["next_offer_no"] == 1  # untouched
    assert body["company_name"] == "Свежо и Вкусно"  # still untouched


async def test_settings_ensure_is_idempotent(client):
    token = await _signed_up_token(client, "test-walt@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    r1 = await client.post("/settings", headers=headers)
    assert r1.status_code == 200
    r2 = await client.post("/settings", headers=headers)
    assert r2.status_code == 200
    assert r1.json() == r2.json()


async def test_settings_require_auth(client):
    r = await client.get("/settings")
    assert r.status_code == 401
    r = await client.patch("/settings", json={"company_name": "x"})
    assert r.status_code == 401


async def test_settings_are_isolated_per_owner(client):
    token_a = await _signed_up_token(client, "test-xena@example.com")
    token_b = await _signed_up_token(client, "test-yves@example.com")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    await client.patch("/settings", headers=headers_a, json={"company_name": "A's company"})

    r = await client.get("/settings", headers=headers_b)
    assert r.json()["company_name"] == ""
