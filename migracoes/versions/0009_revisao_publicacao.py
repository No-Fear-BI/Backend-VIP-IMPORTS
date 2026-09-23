"""Liga a revisao de fornecedores ao catalogo publicado."""
from alembic import op
import sqlalchemy as sa

revision = '0009_revisao_publicacao'
down_revision = '0008_merge_cores_revisao'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('review_decisions', sa.Column('produto_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_revisao_produto', 'review_decisions', 'produtos', ['produto_id'], ['id'], ondelete='SET NULL')
    op.create_unique_constraint('uq_revisao_produto', 'review_decisions', ['produto_id'])


def downgrade():
    op.drop_constraint('uq_revisao_produto', 'review_decisions', type_='unique')
    op.drop_constraint('fk_revisao_produto', 'review_decisions', type_='foreignkey')
    op.drop_column('review_decisions', 'produto_id')
