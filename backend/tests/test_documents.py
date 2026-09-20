import asyncio

import pytest

pytestmark = pytest.mark.asyncio


async def _signed_up_token(client, email: str) -> str:
    r = await client.post("/auth/signup", json={"email": email, "password": "whatever123"})
    return r.json()["access_token"]


def _minimal_document(**overrides):
    body = {
        "date": "2026-01-15",
        "customer_id": None,
        "customer_name": "Walk-in",
        "customer_snapshot": None,
        "items": [{"name": "Ябълки", "qty": 5, "price": 2, "unit": "кг"}],
        "vat_rate": 20,
        "subtotal": 10,
        "vat_amount": 2,
        "total": 12,
        "paid": False,
        "payment_method": "cash",
    }
    body.update(overrides)
    return body


async def test_next_document_number_increments_per_type_independently(client):
    token = await _signed_up_token(client, "test-karl@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    # Counters default to 1 (mirrors supabase/schema.sql), so the first
    # issued number is 1, not 0 — real invoices aren't numbered from zero.
    for expected in (1, 2, 3):
        r = await client.post("/documents/next-number", headers=headers, json={"doc_type": "invoice"})
        assert r.status_code == 200
        assert r.json()["number"] == expected

    # A separate counter for offers, unaffected by the invoice counter above.
    r = await client.post("/documents/next-number", headers=headers, json={"doc_type": "offer"})
    assert r.json()["number"] == 1

    r = await client.post("/documents/next-number", headers=headers, json={"doc_type": "invoice"})
    assert r.json()["number"] == 4


async def test_next_document_number_is_race_free_under_concurrency(client):
    # The entire reason this rewrite exists (see the README's history and
    # docs/python-backend-plan.md): two simultaneous requests must never get
    # the same number. Fire 20 concurrent requests at the same counter and
    # check the results are exactly {1..20}, no duplicates and no gaps.
    token = await _signed_up_token(client, "test-concurrent@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    responses = await asyncio.gather(*[
        client.post("/documents/next-number", headers=headers, json={"doc_type": "invoice"})
        for _ in range(20)
    ])
    numbers = sorted(r.json()["number"] for r in responses)
    assert numbers == list(range(1, 21))


async def test_document_crud(client):
    token = await _signed_up_token(client, "test-lena@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.get("/documents", headers=headers)
    assert r.status_code == 200
    assert r.json() == []

    num = (await client.post("/documents/next-number", headers=headers, json={"doc_type": "invoice"})).json()["number"]
    body = _minimal_document(doc_type="invoice", number=num)
    r = await client.post("/documents", headers=headers, json=body)
    assert r.status_code == 201
    created = r.json()
    assert created["doc_type"] == "invoice"
    assert created["number"] == num
    assert created["total"] == 12
    doc_id = created["id"]

    r = await client.get("/documents", headers=headers)
    assert [d["id"] for d in r.json()] == [doc_id]

    # Editing only ever sends the mutable subset (no doc_type/number).
    edit_body = _minimal_document(customer_name="Renamed buyer", total=99, subtotal=90, vat_amount=9)
    r = await client.put(f"/documents/{doc_id}", headers=headers, json=edit_body)
    assert r.status_code == 200
    updated = r.json()
    assert updated["customer_name"] == "Renamed buyer"
    assert updated["total"] == 99
    assert updated["doc_type"] == "invoice"  # unchanged
    assert updated["number"] == num  # unchanged

    r = await client.patch(f"/documents/{doc_id}/paid", headers=headers, json={"paid": True})
    assert r.status_code == 200
    assert r.json()["paid"] is True

    r = await client.delete(f"/documents/{doc_id}", headers=headers)
    assert r.status_code == 204

    r = await client.get("/documents", headers=headers)
    assert r.json() == []


async def test_link_document_customer(client):
    token = await _signed_up_token(client, "test-mona@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    num = (await client.post("/documents/next-number", headers=headers, json={"doc_type": "offer"})).json()["number"]
    r = await client.post("/documents", headers=headers, json=_minimal_document(doc_type="offer", number=num))
    doc_id = r.json()["id"]

    r = await client.post("/customers", headers=headers, json={"name": "New customer"})
    customer_id = r.json()["id"]

    r = await client.patch(f"/documents/{doc_id}/customer", headers=headers, json={"customer_id": customer_id})
    assert r.status_code == 204

    r = await client.get("/documents", headers=headers)
    assert r.json()[0]["customer_id"] == customer_id


async def test_credit_note_fields_round_trip(client):
    token = await _signed_up_token(client, "test-nina@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    inv_num = (await client.post("/documents/next-number", headers=headers, json={"doc_type": "invoice"})).json()["number"]
    r = await client.post("/documents", headers=headers, json=_minimal_document(doc_type="invoice", number=inv_num))
    invoice = r.json()

    credit_num = (await client.post("/documents/next-number", headers=headers, json={"doc_type": "credit"})).json()["number"]
    credit_body = _minimal_document(
        doc_type="credit", number=credit_num, total=-12, subtotal=-10, vat_amount=-2,
        related_invoice_number=invoice["number"],
    )
    r = await client.post("/documents", headers=headers, json=credit_body)
    assert r.status_code == 201
    credit = r.json()
    assert credit["related_invoice_number"] == invoice["number"]
    assert credit["total"] == -12


async def test_documents_require_auth(client):
    r = await client.get("/documents")
    assert r.status_code == 401
    r = await client.post("/documents/next-number", json={"doc_type": "invoice"})
    assert r.status_code == 401


async def test_documents_are_isolated_per_owner(client):
    token_a = await _signed_up_token(client, "test-oscar@example.com")
    token_b = await _signed_up_token(client, "test-paula@example.com")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    num = (await client.post("/documents/next-number", headers=headers_a, json={"doc_type": "invoice"})).json()["number"]
    r = await client.post("/documents", headers=headers_a, json=_minimal_document(doc_type="invoice", number=num))
    doc_id = r.json()["id"]

    r = await client.get("/documents", headers=headers_b)
    assert r.json() == []

    r = await client.put(f"/documents/{doc_id}", headers=headers_b, json=_minimal_document())
    assert r.status_code == 404

    r = await client.patch(f"/documents/{doc_id}/paid", headers=headers_b, json={"paid": True})
    assert r.status_code == 404

    r = await client.delete(f"/documents/{doc_id}", headers=headers_b)
    assert r.status_code == 404

    # B's own numbering starts fresh at 1, unaffected by A's document.
    r = await client.post("/documents/next-number", headers=headers_b, json={"doc_type": "invoice"})
    assert r.json()["number"] == 1


async def test_adjust_stock_decrements_and_restores(client):
    token = await _signed_up_token(client, "test-quinn@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.post("/products", headers=headers, json={"name": "Круши", "stock": 100})
    product_id = r.json()["id"]

    r = await client.post(f"/products/{product_id}/adjust-stock", headers=headers, json={"qty": 30})
    assert r.status_code == 204
    r = await client.get("/products", headers=headers)
    assert r.json()[0]["stock"] == 70

    # Negative qty (a credit-note line) restores stock.
    r = await client.post(f"/products/{product_id}/adjust-stock", headers=headers, json={"qty": -10})
    assert r.status_code == 204
    r = await client.get("/products", headers=headers)
    assert r.json()[0]["stock"] == 80


async def test_adjust_stock_is_noop_when_not_tracked_or_not_owned(client):
    token_a = await _signed_up_token(client, "test-rick@example.com")
    token_b = await _signed_up_token(client, "test-sara@example.com")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # stock=None ("not tracked") stays None, not an error.
    r = await client.post("/products", headers=headers_a, json={"name": "Untracked"})
    product_id = r.json()["id"]
    r = await client.post(f"/products/{product_id}/adjust-stock", headers=headers_a, json={"qty": 5})
    assert r.status_code == 204
    r = await client.get("/products", headers=headers_a)
    assert r.json()[0]["stock"] is None

    # Someone else's product id: silently does nothing, no 404 (matches the
    # original RPC's fire-and-forget semantics).
    r = await client.post("/products", headers=headers_a, json={"name": "Owned by A", "stock": 10})
    a_product_id = r.json()["id"]
    r = await client.post(f"/products/{a_product_id}/adjust-stock", headers=headers_b, json={"qty": 5})
    assert r.status_code == 204
    r = await client.get("/products", headers=headers_a)
    assert next(p for p in r.json() if p["id"] == a_product_id)["stock"] == 10
