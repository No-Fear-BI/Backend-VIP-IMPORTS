"""Pedidos voltam a ser gravados, agora com status.

Reverte, a pedido do dono, a decisão de 05/10/2026 (migração 0019), que apagou
`selecoes` e `selecao_itens`. O painel passa a ter /admin/pedidos: pedidos em
andamento, finalizados e não finalizados, com as peças e os dados do cliente.

O desenho é o do histórico antigo, com nomes novos e o que faltava:
- `pedidos.status` (em_andamento, finalizado, nao_finalizado), mudado pela equipe;
- `pedidos.atualizado_em`, a data da última mudança de status;
- sem `observacao` (nunca foi usada) e sem `quantidade` nos itens (cada linha é uma peça).

O histórico apagado pela 0019 NÃO volta: as tabelas nascem vazias.

Revisão: 0021_pedidos
Anterior: 0020_produto_preco_interno
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0021_pedidos"
down_revision = "0020_produto_preco_interno"
branch_labels = None
depends_on = None

PEDIDO_STATUS = postgresql.ENUM(
    "em_andamento", "finalizado", "nao_finalizado", name="pedido_status", create_type=False
)


def upgrade() -> None:
    op.execute(
        "CREATE TYPE pedido_status AS ENUM ('em_andamento', 'finalizado', 'nao_finalizado')"
    )

    op.create_table(
        "pedidos",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("cliente_id", sa.Integer(), nullable=True),
        # Cópia dos dados do cliente no momento do envio.
        sa.Column("cliente_nome", sa.String(120), nullable=True),
        sa.Column("cliente_email", postgresql.CITEXT(), nullable=False),
        sa.Column("cliente_telefone", sa.String(20), nullable=True),
        sa.Column("status", PEDIDO_STATUS, nullable=False, server_default="em_andamento"),
        sa.Column("total_itens", sa.SmallInteger(), nullable=False),
        sa.Column(
            "criado_em", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "atualizado_em",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_pedidos"),
        # Nulável e SEM cascata: cliente apagado não leva o pedido junto.
        sa.ForeignKeyConstraint(
            ["cliente_id"], ["clientes.id"], name="fk_pedidos_cliente_id_clientes", ondelete="SET NULL"
        ),
        sa.CheckConstraint("total_itens >= 0", name="ck_pedidos_total_itens"),
    )

    op.create_table(
        "pedido_itens",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("pedido_id", sa.Integer(), nullable=False),
        sa.Column("produto_id", sa.Integer(), nullable=True),
        # Tudo abaixo é CONGELADO: cópia em texto do que o cliente viu no momento do envio.
        sa.Column("produto_codigo", sa.String(32), nullable=False),
        sa.Column("produto_nome", sa.String(180), nullable=False),
        sa.Column("marca_nome", sa.String(80), nullable=False),
        sa.Column("categoria_nome", sa.String(80), nullable=False),
        sa.Column("colecao_nome", sa.String(40), nullable=False),
        sa.Column("imagem_url", sa.Text(), nullable=True),
        sa.Column("variacao_tamanho", sa.String(60), nullable=True),
        sa.Column("variacao_cor", sa.String(60), nullable=True),
        sa.Column("ordem", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id", name="pk_pedido_itens"),
        sa.ForeignKeyConstraint(
            ["pedido_id"], ["pedidos.id"], name="fk_pedido_itens_pedido_id_pedidos", ondelete="CASCADE"
        ),
        # Nulável e SEM cascata: produto apagado deixa a linha intacta, só perde o link.
        sa.ForeignKeyConstraint(
            ["produto_id"], ["produtos.id"], name="fk_pedido_itens_produto_id_produtos", ondelete="SET NULL"
        ),
    )

    op.execute("CREATE INDEX ix_pedidos_admin ON pedidos (status, criado_em DESC, id DESC)")
    op.execute("CREATE INDEX ix_pedidos_cliente ON pedidos (cliente_id, criado_em DESC)")
    op.execute("CREATE INDEX ix_pedido_itens_pedido ON pedido_itens (pedido_id, ordem, id)")
    op.execute("CREATE INDEX ix_pedido_itens_produto ON pedido_itens (produto_id)")


def downgrade() -> None:
    op.drop_table("pedido_itens")
    op.drop_table("pedidos")
    op.execute("DROP TYPE pedido_status")
