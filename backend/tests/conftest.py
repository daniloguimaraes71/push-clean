from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import settings
from app.core.db import Base
from app.main import app

# Use SQLite for tests (portable, no external DB required).
# Production uses PostgreSQL via docker-compose.
_test_db_url = settings.test_database_url
if _test_db_url.startswith("postgresql"):
    _test_db_url = "sqlite+aiosqlite:///./test.db"
test_engine: AsyncEngine = create_async_engine(_test_db_url, echo=False)


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


@pytest_asyncio.fixture(autouse=True)
async def _schema() -> AsyncGenerator[None, None]:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
