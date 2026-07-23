import logging
from collections.abc import AsyncGenerator
from datetime import datetime, timezone

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from .config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=False,
    connect_args={"timeout": 30} if settings.database_url.startswith("sqlite") else {},
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


def _park_incompatible_tables(connection) -> list[str]:
    """Rename tables whose columns predate the current models.

    An older ClipForge database has tables with the same names but different
    columns; `create_all` leaves those untouched and every query then fails.
    Renaming keeps the old rows around as `<table>_old_<timestamp>` instead of
    dropping data, and lets the fresh schema be created cleanly.
    """
    inspector = inspect(connection)
    existing = set(inspector.get_table_names())
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    parked: list[str] = []

    for table_name, table in Base.metadata.tables.items():
        if table_name not in existing:
            continue
        actual = {col["name"] for col in inspector.get_columns(table_name)}
        expected = {col.name for col in table.columns}
        if missing := expected - actual:
            backup = f"{table_name}_old_{stamp}"
            connection.execute(text(f'ALTER TABLE "{table_name}" RENAME TO "{backup}"'))
            logger.warning(
                "Table '%s' has an outdated schema (missing %s). Renamed to '%s' "
                "and recreated.",
                table_name,
                ", ".join(sorted(missing)),
                backup,
            )
            parked.append(table_name)
    return parked


async def init_db() -> None:
    from . import models  # noqa: F401  — registers the mappings

    async with engine.begin() as conn:
        await conn.run_sync(_park_incompatible_tables)
        await conn.run_sync(Base.metadata.create_all)
