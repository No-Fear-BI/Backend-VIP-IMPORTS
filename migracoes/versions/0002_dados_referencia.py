"""Dados de referência: as duas coleções fixas.

Só o que o sistema não funciona sem — Feminino e Masculino, com os slugs
exatamente como o contrato usa nas URLs (GET /colecoes/:slug/categorias).
Nada mais aqui: nenhuma marca, nenhum produto, nenhum administrador de
exemplo. Administrador é criado por comando de linha (docs/modelagem-banco.md,
seção 4.15) — conta de admin não é dado de referência do esquema.

Revisão: 0002
Anterior: 0001
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


colecoes = sa.table(
    "colecoes",
    sa.column("nome", sa.String),
    sa.column("slug", sa.String),
    sa.column("ordem", sa.SmallInteger),
)


def upgrade() -> None:
    op.bulk_insert(
        colecoes,
        [
            {"nome": "Feminina", "slug": "feminino", "ordem": 1},
            {"nome": "Masculina", "slug": "masculino", "ordem": 2},
        ],
    )


def downgrade() -> None:
    op.execute("DELETE FROM colecoes WHERE slug IN ('feminino', 'masculino')")
