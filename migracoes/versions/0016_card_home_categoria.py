"""Categoria pode ocupar um dos dois cards de coleção da home (Esquerda / Direita).

Pedido do dono (30/09/2026): no lugar do card "Feminina" (esquerda) ou "Masculina" (direita) da
home, mostrar uma categoria, com a imagem que ele escolher. `card_home` guarda o lado
('esquerda' ou 'direita'; nulo = não ocupa card) e `card_home_imagem_url` a imagem do card.
Cada lado tem no máximo UMA categoria (índice único parcial).

Revisão: 0016_card_home_categoria
Anterior: 0015_genero_no_produto
"""

from alembic import op
import sqlalchemy as sa

revision = "0016_card_home_categoria"
down_revision = "0015_genero_no_produto"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("categorias", sa.Column("card_home", sa.String(10), nullable=True))
    op.add_column("categorias", sa.Column("card_home_imagem_url", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_categorias_card_home", "categorias", "card_home IN ('esquerda', 'direita')"
    )
    op.create_index(
        "uq_categorias_card_home",
        "categorias",
        ["card_home"],
        unique=True,
        postgresql_where=sa.text("card_home IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_categorias_card_home", table_name="categorias")
    op.drop_constraint("ck_categorias_card_home", "categorias", type_="check")
    op.drop_column("categorias", "card_home_imagem_url")
    op.drop_column("categorias", "card_home")
