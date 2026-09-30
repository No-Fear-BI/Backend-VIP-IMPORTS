"""Produto ganha `em_novidades`: a equipe pode tirá-lo da página Novidades.

Pedido do dono (30/09/2026): na Revisão, marcar se o produto entra em Novidades ao ser aprovado
e, na aba Produtos, remover da página Novidades antes dos 14 dias. A janela de 14 dias continua
valendo: aparece em Novidades quem tem `em_novidades` E foi criado nos últimos 14 dias.
Todo produto existente nasce com a flag ligada (comportamento de antes).

Revisão: 0017_produto_em_novidades
Anterior: 0016_card_home_categoria
"""

from alembic import op
import sqlalchemy as sa

revision = "0017_produto_em_novidades"
down_revision = "0016_card_home_categoria"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "produtos",
        sa.Column("em_novidades", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )


def downgrade() -> None:
    op.drop_column("produtos", "em_novidades")
