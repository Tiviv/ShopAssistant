import json

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import app

# WebSocket testing needs Starlette's TestClient (sync, its own event loop
# under the hood) rather than the async httpx client the other tests use —
# httpx itself has no WebSocket support.


def _signed_up_token(client: TestClient, email: str) -> str:
    r = client.post("/auth/signup", json={"email": email, "password": "whatever123"})
    return r.json()["access_token"]


def test_realtime_rejects_missing_or_invalid_token():
    with TestClient(app) as client:
        # The server closes right after accept-then-reject, so the raise
        # happens on connect itself, not on a later read.
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/ws?token=not-a-real-token"):
                pass
        assert exc_info.value.code == 4401


def test_realtime_broadcasts_product_changes_to_connected_socket():
    with TestClient(app) as client:
        token = _signed_up_token(client, "test-realtime-a@example.com")

        with client.websocket_connect(f"/ws?token={token}") as ws:
            r = client.post(
                "/products", headers={"Authorization": f"Bearer {token}"},
                json={"name": "Ябълки", "price": 2},
            )
            assert r.status_code == 201

            message = json.loads(ws.receive_text())
            assert message == {"table": "products"}


def test_realtime_does_not_cross_owners():
    with TestClient(app) as client:
        token_a = _signed_up_token(client, "test-realtime-b@example.com")
        token_b = _signed_up_token(client, "test-realtime-c@example.com")

        with client.websocket_connect(f"/ws?token={token_a}") as ws_a:
            # B's change must never reach A's socket.
            r = client.post(
                "/customers", headers={"Authorization": f"Bearer {token_b}"},
                json={"name": "B's customer"},
            )
            assert r.status_code == 201

            # A's own change still arrives, proving the socket is alive and
            # listening — B's change was skipped, not just delayed.
            r = client.post(
                "/customers", headers={"Authorization": f"Bearer {token_a}"},
                json={"name": "A's customer"},
            )
            assert r.status_code == 201
            message = json.loads(ws_a.receive_text())
            assert message == {"table": "customers"}


def test_realtime_covers_documents_and_cash_tables():
    with TestClient(app) as client:
        token = _signed_up_token(client, "test-realtime-d@example.com")
        headers = {"Authorization": f"Bearer {token}"}

        with client.websocket_connect(f"/ws?token={token}") as ws:
            num = client.post("/documents/next-number", headers=headers, json={"doc_type": "invoice"}).json()["number"]
            client.post(
                "/documents", headers=headers,
                json={
                    "doc_type": "invoice", "number": num, "date": "2026-01-01",
                    "customer_id": None, "customer_name": "", "customer_snapshot": None,
                    "items": [], "vat_rate": 20, "subtotal": 10, "vat_amount": 2, "total": 12,
                    "paid": False, "payment_method": "cash",
                },
            )
            assert json.loads(ws.receive_text()) == {"table": "documents"}

            client.post("/cash_entries", headers=headers, json={"date": "2026-01-01", "amount": 5})
            assert json.loads(ws.receive_text()) == {"table": "cash_entries"}

            client.put(
                "/cash_closings/2026-01-01", headers=headers,
                json={"counted_cash": 5, "total": 5, "invoice_count": 0, "entry_count": 1},
            )
            assert json.loads(ws.receive_text()) == {"table": "cash_closings"}
