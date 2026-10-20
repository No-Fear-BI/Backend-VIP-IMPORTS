"""Volta o registro de pedidos, agora para o painel acompanhar quem encomendou e se já pagou.

Pedido do cliente (item 11, aba Pedidos): ver os pedidos feitos, os dados de quem pediu e se
o pagamento já foi confirmado. Substitui a decisão de 05/10/2026 (0019) só neste ponto: o
pedido nasce em `POST /selecoes` com uma CÓPIA dos dados do cliente e dos itens, para o
registro não mudar se o cliente editar o cadastro ou o produto sair do ar. Pagamento é
confirmado pela equipe no painel (a loja não cobra pelo site).

Revisão: 0021_pedidos
Anterior: 0020_produto_preco_interno
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0021_pedidos"
down_revision = "0020_produto_preco_interno"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pedidos",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("cliente_id", sa.Integer(), nullable=True),
        sa.Column("cliente_nome", sa.String(120), nullable=True),
        sa.Column("cliente_email", sa.Text(), nullable=False),
        sa.Column("cliente_telefone", sa.String(20), nullable=True),
        sa.Column("itens", postgresql.JSONB(), nullable=False),
        sa.Column("pago", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("pago_em", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("criado_em", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["cliente_id"], ["clientes.id"], name="fk_pedidos_cliente_id_clientes", ondelete="SET NULL"
        ),
    )
    op.create_index("ix_pedidos_recentes", "pedidos", [sa.text("criado_em DESC"), sa.text("id DESC")])


def downgrade() -> None:
    op.drop_index("ix_pedidos_recentes", table_name="pedidos")
    op.drop_table("pedidos")
