"""Produto ganha `preco_centavos`: preço de consulta INTERNA do dono.

Pedido do dono (06/10/2026): registrar o preço de cada peça no painel (Revisão, criação e edição),
só para ele consultar. A loja continua sem preço: o campo existe só nos esquemas de ADMIN e
`testes/teste_preco_nao_vaza.py` falha se ele aparecer em resposta pública.
Centavos inteiros (R$ 1.234,50 = 123450), opcional, de 0 a R$ 100.000,00. Produto existente fica sem preço.

Revisão: 0018_produto_preco_interno
Anterior: 0017_produto_em_novidades
"""

from alembic import op
import sqlalchemy as sa

revision = "0018_produto_preco_interno"
down_revision = "0017_produto_em_novidades"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("produtos", sa.Column("preco_centavos", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_produtos_preco_centavos",
        "produtos",
        "preco_centavos IS NULL OR (preco_centavos >= 0 AND preco_centavos <= 10000000)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_produtos_preco_centavos", "produtos", type_="check")
    op.drop_column("produtos", "preco_centavos")
