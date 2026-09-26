"""Fila de revisão dos produtos de fornecedores."""
from alembic import op
import sqlalchemy as sa
revision = '0007_revisao_produtos'
down_revision = '0006'
branch_labels = None
depends_on = None
def upgrade():
    if sa.inspect(op.get_bind()).has_table("review_decisions"):
        return
    op.create_table('review_decisions', sa.Column('product_id', sa.String(80), primary_key=True), sa.Column('status', sa.String(12), nullable=False), sa.Column('translated_name', sa.String(240), nullable=False), sa.Column('translated_details', sa.Text(), nullable=False), sa.Column('original_name', sa.Text(), nullable=False), sa.Column('category', sa.String(100), nullable=False), sa.Column('supplier', sa.String(40), nullable=False), sa.Column('image', sa.Text(), nullable=False), sa.Column('source_url', sa.Text(), nullable=False), sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False), sa.CheckConstraint("status IN ('approved', 'rejected')", name='ck_review_decisions_status'))
def downgrade(): op.drop_table('review_decisions')
