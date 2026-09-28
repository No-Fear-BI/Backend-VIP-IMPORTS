"""Semeia a linha única de acesso_config com modo = 'aberto'.

A 0001 criou a tabela mas nenhuma migração inseria a linha: enquanto a seção
05 estava congelada ninguém lia a tabela, e a falta não aparecia. Com o
controle de entrada ligado, a aplicação lê essa linha em toda requisição de
catálogo — e ela precisa existir já no modo aberto. O site NUNCA sobe
bloqueado por migração: quem liga o portão é o administrador, pelo painel
(PATCH /admin/configuracao/acesso).

`ON CONFLICT DO NOTHING`: num banco em que alguém já tenha inserido a linha à
mão, a configuração que está lá é respeitada — esta migração não volta o modo
para 'aberto' por cima de uma decisão já tomada.
"""
from alembic import op

revision = '0013_acesso_config_semente'
down_revision = '0012_merge_destinos_main'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "INSERT INTO acesso_config (id, modo) VALUES (1, 'aberto') "
        "ON CONFLICT (id) DO NOTHING"
    )


def downgrade():
    # Não apaga a linha: ela pode carregar o modo e a mensagem que o painel
    # gravou depois. A aplicação trata linha ausente como 'aberto', então
    # manter a linha num banco rebaixado não muda comportamento nenhum.
    pass
