from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

pytestmark = pytest.mark.asyncio

# "Today" per the same clock the backend itself uses for close-forgotten-days
# (app/routers/cash_closings.py's SHOP_TIMEZONE) — not the test runner's own
# system timezone, which disagrees with Europe/Sofia for a few hours around
# midnight UTC and would otherwise make this test flake depending on when
# it's run.
_today_sofia = datetime.now(ZoneInfo("Europe/Sofia")).date()
PAST_DATE = (_today_sofia - timedelta(days=2)).isoformat()
TODAY = _today_sofia.isoformat()


async def _signed_up_token(client, email: str) -> str:
    r = await client.post("/auth/signup", json={"email": email, "password": "whatever123"})
    return r.json()["access_token"]


async def test_cash_entry_crud(client):
    token = await _signed_up_token(client, "test-tina@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.get("/cash_entries", headers=headers)
    assert r.status_code == 200
    assert r.json() == []

    r = await client.post(
        "/cash_entries", headers=headers,
        json={"date": TODAY, "amount": 15.5, "payment_method": "cash", "note": "Retail sale"},
    )
    assert r.status_code == 201
    entry = r.json()
    assert entry["amount"] == 15.5
    entry_id = entry["id"]

    r = await client.get("/cash_entries", headers=headers)
    assert [e["id"] for e in r.json()] == [entry_id]

    r = await client.delete(f"/cash_entries/{entry_id}", headers=headers)
    assert r.status_code == 204
    r = await client.get("/cash_entries", headers=headers)
    assert r.json() == []


async def test_cash_entries_require_auth_and_are_isolated(client):
    r = await client.get("/cash_entries")
    assert r.status_code == 401

    token_a = await _signed_up_token(client, "test-uma@example.com")
    token_b = await _signed_up_token(client, "test-victor@example.com")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    r = await client.post("/cash_entries", headers=headers_a, json={"date": TODAY, "amount": 5})
    entry_id = r.json()["id"]

    r = await client.get("/cash_entries", headers=headers_b)
    assert r.json() == []

    r = await client.delete(f"/cash_entries/{entry_id}", headers=headers_b)
    assert r.status_code == 404


async def test_cash_closing_upsert_and_reopen(client):
    token = await _signed_up_token(client, "test-wendy@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.get("/cash_closings", headers=headers)
    assert r.json() == []

    body = {
        "counted_cash": 100, "note": "End of day",
        "total_cash": 90, "total_card": 10, "total_bank": 0, "total": 100,
        "invoice_count": 2, "entry_count": 1, "auto_closed": False,
    }
    r = await client.put(f"/cash_closings/{TODAY}", headers=headers, json=body)
    assert r.status_code == 200
    closing = r.json()
    assert closing["date"] == TODAY
    assert closing["counted_cash"] == 100
    assert closing["total"] == 100

    # Upsert: closing the same day again replaces it rather than erroring.
    body["counted_cash"] = 105
    r = await client.put(f"/cash_closings/{TODAY}", headers=headers, json=body)
    assert r.status_code == 200
    assert r.json()["counted_cash"] == 105

    r = await client.get("/cash_closings", headers=headers)
    assert len(r.json()) == 1

    # Reopen.
    r = await client.delete(f"/cash_closings/{TODAY}", headers=headers)
    assert r.status_code == 204
    r = await client.get("/cash_closings", headers=headers)
    assert r.json() == []

    # Reopening an already-open day is a harmless no-op, not an error.
    r = await client.delete(f"/cash_closings/{TODAY}", headers=headers)
    assert r.status_code == 204


async def _issue_invoice(client, headers, *, day: str, total: float, payment_method: str = "cash"):
    num = (await client.post("/documents/next-number", headers=headers, json={"doc_type": "invoice"})).json()["number"]
    body = {
        "doc_type": "invoice", "number": num, "date": day,
        "customer_id": None, "customer_name": "Walk-in", "customer_snapshot": None,
        "items": [], "vat_rate": 20, "subtotal": total, "vat_amount": 0, "total": total,
        "paid": True, "payment_method": payment_method,
    }
    r = await client.post("/documents", headers=headers, json=body)
    assert r.status_code == 201
    return r.json()


async def test_close_forgotten_days_aggregates_and_is_idempotent(client):
    token = await _signed_up_token(client, "test-xander@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    await _issue_invoice(client, headers, day=PAST_DATE, total=50, payment_method="cash")
    await client.post(
        "/cash_entries", headers=headers,
        json={"date": PAST_DATE, "amount": 20, "payment_method": "card", "note": "Till sale"},
    )
    # Today's own activity should NOT be auto-closed — only finished days.
    await _issue_invoice(client, headers, day=TODAY, total=999, payment_method="cash")

    r = await client.post("/cash_closings/close-forgotten-days", headers=headers)
    assert r.status_code == 200
    assert r.json()["closed"] == 1

    r = await client.get("/cash_closings", headers=headers)
    closings = r.json()
    assert len(closings) == 1
    closing = closings[0]
    assert closing["date"] == PAST_DATE
    assert closing["total_cash"] == 50
    assert closing["total_card"] == 20
    assert closing["total"] == 70
    assert closing["invoice_count"] == 1
    assert closing["entry_count"] == 1
    assert closing["auto_closed"] is True
    assert closing["counted_cash"] == 0

    # Idempotent: running it again closes nothing new and leaves the row as is.
    r = await client.post("/cash_closings/close-forgotten-days", headers=headers)
    assert r.json()["closed"] == 0
    r = await client.get("/cash_closings", headers=headers)
    assert len(r.json()) == 1
    assert r.json()[0]["total"] == 70


async def test_close_forgotten_days_is_isolated_per_owner(client):
    token_a = await _signed_up_token(client, "test-yara@example.com")
    token_b = await _signed_up_token(client, "test-zane@example.com")
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    await _issue_invoice(client, headers_a, day=PAST_DATE, total=40, payment_method="cash")
    # B has no activity at all.

    r = await client.post("/cash_closings/close-forgotten-days", headers=headers_b)
    assert r.json()["closed"] == 0
    r = await client.get("/cash_closings", headers=headers_b)
    assert r.json() == []

    r = await client.post("/cash_closings/close-forgotten-days", headers=headers_a)
    assert r.json()["closed"] == 1
