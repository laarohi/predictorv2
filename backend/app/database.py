"""Database engine and session management.

Schema is managed exclusively by Alembic — `init_db()` runs
`alembic upgrade head` on every backend startup so any newly-added
migration files apply automatically. This is the single source of truth
for table shapes; nothing else (including SQLModel.metadata.create_all)
creates tables at runtime, which prevents the schema drift that happens
when two systems both believe they own the question of "what's in the DB".

Workflow for adding a new table or column:
  1. Add/modify the SQLModel class under app/models/ and import it in
     models/__init__.py
  2. Run `alembic revision --autogenerate -m "describe change"` inside
     the backend container to produce a migration file
  3. Review the generated migration; commit it
  4. Restart the backend → init_db() applies it on next boot
"""

import asyncio
import logging
from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings


logger = logging.getLogger(__name__)


def get_async_engine():
    """Create async database engine."""
    settings = get_settings()
    db_url = str(settings.database_url).replace("postgresql://", "postgresql+asyncpg://")
    return create_async_engine(
        db_url,
        echo=settings.database_echo,
        future=True,
    )


engine = get_async_engine()

async_session_maker = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


def _alembic_ini_path() -> Path:
    """Resolve alembic.ini regardless of cwd. This file lives at
    /app/app/database.py inside the container; the ini sits at /app/alembic.ini.
    """
    return Path(__file__).resolve().parent.parent / "alembic.ini"


async def init_db() -> None:
    """Apply pending Alembic migrations to bring the DB to `head`.

    Runs on every backend startup. Idempotent: if the DB is already at
    head, alembic does a quick version-check and returns. Typical cold-
    boot cost is <200ms; applying actual pending migrations may take a
    few seconds.

    A failure here intentionally takes the app down at startup — that's
    the safe default for a schema-versioned system. Logs surface the
    underlying error.
    """
    from alembic import command
    from alembic.config import Config

    ini_path = _alembic_ini_path()
    if not ini_path.exists():
        logger.warning("alembic.ini not found at %s — skipping migrations", ini_path)
        return

    cfg = Config(str(ini_path))
    # alembic.command.upgrade is synchronous and internally spins up its
    # own sync engine + asyncio.run() inside env.py's run_migrations_online.
    # Running it via asyncio.to_thread() keeps it off the main event loop
    # so the nested asyncio.run() doesn't trip "another loop is running".
    logger.info("Running alembic upgrade head…")
    await asyncio.to_thread(command.upgrade, cfg, "head")
    logger.info("alembic upgrade head complete")


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield database session."""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
