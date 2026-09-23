"""Permite exibir o mesmo produto em mais de uma colecao."""
from alembic import op
import sqlalchemy as sa

revision = '0011_produto_destinos'
down_revision = '0010_revisao_historico'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'produto_categorias_adicionais',
        sa.Column('produto_id', sa.Integer(), nullable=False),
        sa.Column('categoria_id', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('produto_id', 'categoria_id'),
        sa.ForeignKeyConstraint(['produto_id'], ['produtos.id'], name='fk_destino_produto', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['categoria_id'], ['categorias.id'], name='fk_destino_categoria', ondelete='RESTRICT'),
    )


def downgrade():
    op.drop_table('produto_categorias_adicionais')
