import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.database import async_session
from app.main import app
from app.models import User


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture(autouse=True)
async def cleanup_test_users():
    # Runs against the real dev database (see backend/README.md) — no mocks,
    # so this deletes anything a test created (cascades to its settings row)
    # rather than leaving fixtures behind between runs.
    yield
    async with async_session() as session:
        await session.execute(delete(User).where(User.email.like("test-%@example.com")))
        await session.commit()
