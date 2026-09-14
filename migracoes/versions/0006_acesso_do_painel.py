"""Ajustes de esquema para o acesso do painel (tarefas 52 e 53).

O QUE ESTA REVISÃO **NÃO** FAZ: criar `administradores` e `admin_sessoes`.
As duas já existem desde a 0001, com todas as colunas que o painel precisa —
e-mail citext único, `senha_hash`, `ativo`, `criado_em`, `senha_alterada_em`,
mais a tabela de sessão própria com hash do token, `expira_em`, `revogado_em`,
ip e user agent. Foi decisão registrada (modelagem, 6.12): modelar o acesso
antes de implementar, porque alterar essas tabelas depois, com base cheia, é
exatamente o que o plano existe para evitar. Quem procurar o "CREATE TABLE
administradores" vai achar na 0001, não aqui.

O que sobrou de verdade para esta revisão:

1. E-MAIL GRAVADO EM MINÚSCULAS. `citext` já resolve a COMPARAÇÃO — "Jose@X"
   e "jose@x" são a mesma linha, e é por isso que o projeto usa citext em vez
   de lower() na aplicação (modelagem, 6.10). O que o citext não faz é decidir
   a FORMA GRAVADA: quem escrever "Jose@X.com" fica com isso na tabela e
   aparece assim no painel e no log. Escrevem nesta tabela dois comandos de
   linha, e amanhã talvez um CRUD; a CHECK vale mais que a disciplina de três
   chamadores.

2. TENTATIVAS DE LOGIN DO ADMIN: reaproveitam `tentativas_acesso`, sem tabela
   nova. A tabela já é genérica — a chave é (escopo, ip, janela), e o `escopo`
   nasceu na 0004 justamente para o login do painel entrar depois sem misturar
   contagem. O que NÃO pode acontecer é os dois lados somarem no mesmo
   balde: um visitante teimoso na identificação trancaria o login do painel, e
   o admin ficaria de fora do próprio sistema por causa de alguém que ele não
   controla. Por isso a identificação do cliente conta em 'identificacao' e o
   login do painel em 'admin_login' — mesma tabela, baldes separados, cada um
   com seu limite. Isso é constante de aplicação (seguranca/limite.py), não
   DDL: nada a migrar aqui, só a decisão registrada.

NÃO ENTRA AQUI, e é de propósito: índice em `admin_sessoes (administrador_id)`.
A troca de senha revoga as sessões daquele administrador com um UPDATE por
`administrador_id`, mas são duas contas no lançamento e a operação é rara —
varrer algumas centenas de linhas nesse momento custa menos que manter um
índice escrito a cada login. A decisão já estava na lista de índices
descartados da modelagem; segue valendo, agora com o chamador à vista.

Revisão: 0006
Anterior: 0005
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Normaliza o que já estiver gravado antes de exigir a forma nova: com a
    # CHECK criada primeiro, uma linha "Jose@X.com" derrubaria a migração.
    op.execute("UPDATE administradores SET email = lower(email) WHERE email <> lower(email)")
    # `email = lower(email)` NÃO é tautologia aqui, apesar da coluna ser
    # citext: `lower()` devolve text, e comparar citext com text cai no
    # operador de text, que diferencia caixa. É a comparação que se quer.
    op.execute(
        "ALTER TABLE administradores "
        "ADD CONSTRAINT ck_administradores_email_minusculo "
        "CHECK (email = lower(email))"
    )


def downgrade() -> None:
    # Só a restrição sai. Os e-mails continuam em minúsculas, e devem mesmo:
    # desfazer a normalização exigiria saber a forma original, que ninguém
    # guardou — e não faria falta a ninguém.
    op.execute(
        "ALTER TABLE administradores DROP CONSTRAINT ck_administradores_email_minusculo"
    )
