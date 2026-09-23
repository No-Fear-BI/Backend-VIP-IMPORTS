"""Distingue aprovacoes antigas de produtos posteriormente excluidos."""
from alembic import op
import sqlalchemy as sa

revision = '0010_revisao_historico'
down_revision = '0009_revisao_publicacao'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('review_decisions', sa.Column('publicado_no_catalogo', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.execute('UPDATE review_decisions SET publicado_no_catalogo = true WHERE produto_id IS NOT NULL')


def downgrade():
    op.drop_column('review_decisions', 'publicado_no_catalogo')
