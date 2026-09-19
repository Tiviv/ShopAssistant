from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config import settings

# NullPool: a fresh physical connection per checkout instead of a reused
# pool. At this app's scale (one shop, a handful of concurrent users) the
# pooling performance doesn't matter, and it sidesteps a real footgun —
# asyncpg connections are bound to the event loop that created them, and a
# pooled connection handed back under a different loop (every dev-server
# reload, every pytest-asyncio test) raises "another operation is in
# progress" instead of a clear error.
engine = create_async_engine(settings.database_url, echo=False, poolclass=NullPool)
async_session = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session
