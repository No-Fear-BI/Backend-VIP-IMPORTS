"""Quantidade total informada pela equipe; null significa não informada."""

from alembic import op
import sqlalchemy as sa

revision = '0018_quantidade_disponivel'
down_revision = '0017_produto_em_novidades'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('produtos', sa.Column('quantidade_disponivel', sa.Integer(), nullable=True))
    op.create_check_constraint('ck_produtos_quantidade_disponivel', 'produtos', 'quantidade_disponivel >= 0')


def downgrade() -> None:
    op.drop_constraint('ck_produtos_quantidade_disponivel', 'produtos', type_='check')
    op.drop_column('produtos', 'quantidade_disponivel')
