import re

import pytest
from aiosmtpd.controller import Controller

from app.config import settings

pytestmark = pytest.mark.asyncio


class _CapturingHandler:
    def __init__(self):
        self.messages: list[str] = []

    async def handle_DATA(self, server, session, envelope):
        self.messages.append(envelope.content.decode("utf8", errors="replace"))
        return "250 Message accepted for delivery"


@pytest.fixture
def smtp_catcher(monkeypatch):
    handler = _CapturingHandler()
    # A fixed, unlikely-to-collide port rather than 0: this aiosmtpd version
    # doesn't resolve an OS-assigned port back onto the Controller before
    # its own startup check tries to connect to it.
    controller = Controller(handler, hostname="127.0.0.1", port=10250)
    controller.start()
    # Patched directly on the live settings singleton, not just the module
    # name — app/email.py does `from app.config import settings` and reads
    # attributes off that same object at call time.
    monkeypatch.setattr(settings, "smtp_host", controller.hostname)
    monkeypatch.setattr(settings, "smtp_port", controller.port)
    monkeypatch.setattr(settings, "smtp_use_tls", False)
    try:
        yield handler
    finally:
        controller.stop()


def _extract_reset_token(email_text: str) -> str:
    match = re.search(r"reset_token=(\S+)", email_text)
    assert match, f"no reset link found in email:\n{email_text}"
    return match.group(1)


async def test_forgot_password_sends_email_with_working_link(client, smtp_catcher):
    email = "test-zeus@example.com"
    await client.post("/auth/signup", json={"email": email, "password": "original-password"})

    r = await client.post("/auth/forgot-password", json={"email": email})
    assert r.status_code == 200
    assert len(smtp_catcher.messages) == 1
    assert email in smtp_catcher.messages[0]

    token = _extract_reset_token(smtp_catcher.messages[0])

    r = await client.post("/auth/reset-password", json={"token": token, "new_password": "brand-new-password"})
    assert r.status_code == 200

    # Old password no longer works, new one does.
    r = await client.post("/auth/login", json={"email": email, "password": "original-password"})
    assert r.status_code == 401
    r = await client.post("/auth/login", json={"email": email, "password": "brand-new-password"})
    assert r.status_code == 200


async def test_reset_token_is_single_use(client, smtp_catcher):
    email = "test-aria@example.com"
    await client.post("/auth/signup", json={"email": email, "password": "original-password"})
    await client.post("/auth/forgot-password", json={"email": email})
    token = _extract_reset_token(smtp_catcher.messages[0])

    r = await client.post("/auth/reset-password", json={"token": token, "new_password": "first-new-password"})
    assert r.status_code == 200

    # Same token again — must be rejected, not silently accepted a second time.
    r = await client.post("/auth/reset-password", json={"token": token, "new_password": "second-new-password"})
    assert r.status_code == 400


async def test_reset_password_rejects_unknown_token(client):
    r = await client.post("/auth/reset-password", json={"token": "not-a-real-token", "new_password": "whatever123"})
    assert r.status_code == 400


async def test_forgot_password_does_not_reveal_whether_email_exists(client, smtp_catcher):
    r = await client.post("/auth/forgot-password", json={"email": "test-nobody-registered@example.com"})
    assert r.status_code == 200
    # Same response shape either way, and no email actually sent for an
    # unregistered address.
    assert smtp_catcher.messages == []


async def test_forgot_password_falls_back_to_logging_when_smtp_unconfigured(client, caplog):
    # No smtp_catcher fixture here — settings.smtp_host stays "" (the
    # default), which app/email.py treats as "log the link instead of
    # emailing it" rather than failing the request.
    email = "test-boris@example.com"
    await client.post("/auth/signup", json={"email": email, "password": "whatever123"})

    with caplog.at_level("WARNING"):
        r = await client.post("/auth/forgot-password", json={"email": email})
    assert r.status_code == 200
    assert any("reset link" in rec.message for rec in caplog.records)
