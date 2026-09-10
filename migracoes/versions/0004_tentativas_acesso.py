"""Tabela de contagem de tentativas de acesso por IP (tarefa 42).

POR QUE NO BANCO E NÃO EM MEMÓRIA: no VPS o uvicorn roda com mais de um
worker. Um contador em memória vive dentro de um processo só — o worker 2 não
enxerga o que o worker 1 contou, e o limite vira decorativo: basta a
requisição cair no outro worker para passar.

Janela fixa de um minuto, uma linha por (escopo, ip, janela), incrementada por
UPSERT. Janela fixa deixa passar uma rajada na virada do minuto; para conter
abuso automatizado de identificação isso é suficiente e custa uma linha por
IP por minuto, em vez de uma linha por tentativa.

`escopo` existe para o login do administrador (amanhã) usar a mesma tabela sem
misturar contagem com a identificação de cliente. Isto é limite por IP, não
autenticação: não há token nem sessão aqui, então compartilhar a tabela não
cria o risco que separa as duas camadas de sessão.

Revisão: 0004
Anterior: 0003
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tentativas_acesso",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("escopo", sa.String(30), nullable=False),
        sa.Column("ip", postgresql.INET(), nullable=False),
        # Início do minuto (timestamp truncado), não o instante da tentativa.
        sa.Column("janela", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("tentativas", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id", name="pk_tentativas_acesso"),
        sa.UniqueConstraint(
            "escopo", "ip", "janela", name="uq_tentativas_acesso_escopo_ip_janela"
        ),
        sa.CheckConstraint("tentativas > 0", name="ck_tentativas_acesso_positivas"),
    )
    # Diferente das outras tabelas, esta cresce por si: uma linha por IP por
    # minuto, para sempre. A limpeza das janelas velhas não é opcional, e sem
    # este índice ela varreria a tabela inteira toda vez.
    op.execute("CREATE INDEX ix_tentativas_acesso_janela ON tentativas_acesso (janela)")


def downgrade() -> None:
    op.drop_table("tentativas_acesso")
