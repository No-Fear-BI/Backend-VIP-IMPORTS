"""Loja sempre fechada: acesso_config.modo = 'aprovacao'.

O cliente decidiu que a loja fica fechada o tempo todo. Isso inverte a premissa
da 0013 ("o site nunca sobe bloqueado por migração"): agora ela sobe bloqueada,
de propósito, e só entra quem a equipe liberar pelo painel.

Ninguém é trancado para fora: os clientes que já existiam continuam
'aprovado', porque é esse o default de clientes.acesso_status. Só quem se
identificar depois disto, com e-mail novo, nasce 'pendente'. O /admin/*
continua fora do portão.

Grava a linha com upsert (a 0013 pode ter deixado 'aberto', ou o banco pode
não ter linha nenhuma) e troca o DEFAULT da coluna, para que uma linha criada
sem modo também nasça fechada. O valor 'aberto' continua no enum acesso_modo.
"""
from alembic import op

revision = '0014_loja_sempre_fechada'
down_revision = '0013_acesso_config_semente'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "INSERT INTO acesso_config (id, modo) VALUES (1, 'aprovacao') "
        "ON CONFLICT (id) DO UPDATE SET modo = 'aprovacao'"
    )
    op.execute("ALTER TABLE acesso_config ALTER COLUMN modo SET DEFAULT 'aprovacao'")


def downgrade():
    op.execute("ALTER TABLE acesso_config ALTER COLUMN modo SET DEFAULT 'aberto'")
    op.execute("UPDATE acesso_config SET modo = 'aberto' WHERE id = 1")
