"""Remove definitivamente o histórico de pedidos; a conversa fica no WhatsApp."""
from alembic import op

revision = '0019_sem_historico_pedidos'
down_revision = '0018_quantidade_disponivel'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.drop_table('selecao_itens')
    op.drop_table('selecoes')

def downgrade() -> None:
    raise RuntimeError('O histórico removido não pode ser recuperado por downgrade.')
