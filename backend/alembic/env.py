import sys
import os
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

# Make sure the app package is importable from this file's location
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Alembic config object — reads alembic.ini
config = context.config

# Set up Python logging as defined in alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import our app's settings and SQLModel metadata.
# This tells Alembic about our table definitions so it can:
#   - generate migrations automatically (alembic revision --autogenerate)
#   - know what the target schema should look like
from app.core.config import settings
from app.models.memory import ChatMessage, SessionHistory  # noqa: F401 — imports register the tables
from sqlmodel import SQLModel

# Override the sqlalchemy.url from alembic.ini with the one from our settings.
# This means there is one source of truth for the database URL: the .env file.
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    """
    Offline mode: generate SQL script without connecting to a live database.
    Useful for reviewing migrations or applying them manually.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Online mode: connect to the live database and apply migrations directly.
    This is what `alembic upgrade head` runs.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
