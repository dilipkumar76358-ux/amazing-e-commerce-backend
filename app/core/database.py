from typing import AsyncGenerator, Optional
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.config import settings

engine = None
AsyncSessionLocal = None

if settings.DATABASE_URL and "placeholder" not in settings.DATABASE_URL and settings.DATABASE_URL.startswith("postgresql"):
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=settings.ENVIRONMENT == "development",
        pool_size=10,
        max_overflow=20
    )
    AsyncSessionLocal = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False
    )


async def get_db() -> AsyncGenerator[Optional[AsyncSession], None]:
    """Dependency for obtaining async SQLAlchemy database session."""
    if AsyncSessionLocal is None:
        yield None
        return
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
