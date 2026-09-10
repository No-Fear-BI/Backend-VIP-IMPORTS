"""Ambiente de execução do Alembic.

`target_metadata` aponta para os modelos (tarefa 15) para sustentar
`alembic check` — a prova de que os modelos espelham fielmente o banco.

Isso NÃO transforma os modelos em fonte da verdade: as migrações continuam
sendo. `--autogenerate` aqui serve para conferir divergência, não para gerar
migração sem revisão.
"""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from vip_api.modelos import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    """Lê a URL do banco do ambiente. Nunca do alembic.ini."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL não está definida no ambiente. "
            "Copie .env.example para .env e exporte as variáveis antes de rodar o Alembic."
        )
    return url


def run_migrations_offline() -> None:
    """Gera o SQL das migrações sem conectar no banco (`alembic upgrade head --sql`)."""
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Conecta no banco e aplica as migrações — o modo normal do dia a dia."""
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
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
