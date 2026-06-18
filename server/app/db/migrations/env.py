from __future__ import annotations

from logging.config import fileConfig

from alembic import context

from app.config import load_runtime_config
from app.db.base import Base
from DaliCommonLib.dali_db_man import DbMan

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

alembic_args = context.get_x_argument(as_dictionary=True)
load_runtime_config(alembic_args.get("config"))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = DbMan.get_connect_str()
    schema = DbMan.get_active_db()
    context.configure(
        url=f"{url}{schema}?charset=utf8mb4",
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = DbMan.get_db_engine()

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
