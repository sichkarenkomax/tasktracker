"""Alembic environment.

The database URL always comes from the application settings, so migrations use
exactly the same configuration as the running application
(docs/architecture.md, section 46).
"""

from __future__ import annotations

import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Import every model so that autogenerate sees the full metadata.
import app.database.models  # noqa: F401
from app.config import get_settings
from app.core.modules.registry import import_module_packages
from app.database.base import Base

# Module-owned models must be registered too, even for modules that are
# disabled at runtime (docs/architecture.md, section 46).
import_module_packages()

config = context.config

if config.config_file_name is not None:
    # Alembic is a guest in the application's logging setup. The default
    # disable_existing_loggers=True would silence every logger that already
    # exists, which is invisible in production (migrations run in their own
    # process) but breaks in-process callers such as the test suite.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# `%` is an interpolation marker in configparser - escape it.
config.set_main_option(
    "sqlalchemy.url",
    get_settings().database_url.replace("%", "%%"),
)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
