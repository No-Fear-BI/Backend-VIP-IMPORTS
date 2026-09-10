"""Base declarativa e os tipos enumerados compartilhados.

AVISO QUE VALE PARA TODO O PACOTE `modelos`: estes modelos ESPELHAM as
migrações já aplicadas — as migrações são a fonte da verdade do schema, não
eles. Nunca gere migração por autogenerate a partir daqui sem revisar linha a
linha. `alembic check` existe para provar que o espelho está fiel; se ele
acusar divergência, o modelo é que está errado.
"""

from sqlalchemy import MetaData
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import DeclarativeBase

# Só a PK segue convenção automática (pk_<tabela>, uniforme em todas as
# migrações). Unique, FK e check têm nomes que não seguem regra única, então
# vão nomeados à mão em cada modelo.
CONVENCAO_NOMES = {"pk": "pk_%(table_name)s"}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=CONVENCAO_NOMES)


# create_type=False: os tipos já existem no banco, criados pela migração 0001.
PRODUTO_STATUS = ENUM(
    "normal", "esgotado", "oculto", name="produto_status", create_type=False
)
ACESSO_MODO = ENUM(
    "aberto", "senha_compartilhada", "aprovacao", name="acesso_modo", create_type=False
)
ACESSO_SITUACAO = ENUM(
    "pendente", "aprovado", "recusado", name="acesso_situacao", create_type=False
)
VARIACAO_TIPO = ENUM("tamanho", "cor", name="variacao_tipo", create_type=False)
