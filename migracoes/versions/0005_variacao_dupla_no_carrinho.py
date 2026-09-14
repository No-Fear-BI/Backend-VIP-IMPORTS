"""Uma variação de cada tipo por item do carrinho, e não uma variação só.

POR QUE: o contrato mostra a seleção como "(Chanel, M / Preto)" e a página do
produto tem seletor de tamanho E de cor. Com uma coluna `variacao_id` só, o
cliente escolhia um ou outro — o fluxo que gera venda nascia quebrado.

POR QUE DUAS COLUNAS E NÃO UMA TABELA DE LIGAÇÃO: `variacao_tipo` é enum
fechado em dois valores. Uma coluna nulável por tipo dá "no máximo um de cada"
de graça, sem tabela intermediária e sem regra em código para contar quantas
variações de cada tipo o item já tem.

COMO O BANCO IMPEDE COR NA COLUNA DE TAMANHO: uma CHECK sozinha não enxerga
outra tabela — CHECK não aceita subconsulta. Então o tipo vem junto na linha,
em `variacao_tamanho_tipo` / `variacao_cor_tipo`, colunas de valor constante
preenchidas pelo DEFAULT (nenhuma rota escreve nelas). A CHECK prende cada uma
ao seu valor, e a FK COMPOSTA para `produto_variacoes (id, tipo)` prova que o
tipo declarado é o tipo real da variação apontada. As duas juntas fecham o
caso: gravar o id de uma cor em `variacao_tamanho_id` estoura a FK; gravar
'cor' na coluna de tipo estoura a CHECK. É o mesmo padrão que
`produtos (categoria_id, colecao_id)` já usa desde a 0001.

`ON DELETE SET NULL (variacao_tamanho_id)` — com a lista de colunas, sintaxe do
PostgreSQL 15 — zera só o id quando a variação é apagada. Sem a lista, o
PostgreSQL tentaria zerar também a coluna de tipo, que é NOT NULL.

TAMBÉM AQUI, e não numa migração futura:

- `carrinho_itens.quantidade` e `selecao_itens.quantidade` saem. Estão sem uso
  desde que ficou decidido que catálogo de seleção não tem quantidade; nenhuma
  rota lê ou escreve as duas. Coluna morta é coluna que alguém vai tentar usar.
- `selecao_itens` troca `variacao_tipo`/`variacao_valor` por
  `variacao_tamanho`/`variacao_cor`. A seleção é dado CONGELADO: se a linha só
  guardasse uma variação, o item enviado como "M / Preto" voltaria do histórico
  como "M", e o congelamento deixaria de ser fiel ao que o cliente viu.

PERDA DE DADO NO DOWNGRADE: voltar para uma coluna só não tem como preservar
duas variações. O `downgrade` mantém o tamanho quando existe (a cor, quando não
há tamanho) e descarta a outra — e colapsa as linhas que passam a colidir no
UNIQUE antigo. Está escrito no código, no ponto exato em que acontece.

Revisão: 0005
Anterior: 0004
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ==================================================================
    # Alvo da FK composta
    # ==================================================================
    # (id, tipo) precisa ser único para poder ser referenciado, mesmo com `id`
    # já sendo PK: o PostgreSQL exige unicidade declarada no PAR exato.
    op.execute(
        "ALTER TABLE produto_variacoes "
        "ADD CONSTRAINT uq_produto_variacoes_id_tipo UNIQUE (id, tipo)"
    )

    # ==================================================================
    # carrinho_itens: variacao_id -> (variacao_tamanho_id, variacao_cor_id)
    # ==================================================================
    op.add_column("carrinho_itens", sa.Column("variacao_tamanho_id", sa.Integer(), nullable=True))
    op.add_column("carrinho_itens", sa.Column("variacao_cor_id", sa.Integer(), nullable=True))
    op.execute(
        "ALTER TABLE carrinho_itens "
        "ADD COLUMN variacao_tamanho_tipo variacao_tipo NOT NULL DEFAULT 'tamanho', "
        "ADD COLUMN variacao_cor_tipo variacao_tipo NOT NULL DEFAULT 'cor'"
    )

    # Cada item existente tem no máximo uma variação: ela vai para a coluna do
    # seu próprio tipo, ninguém precisa escolher.
    op.execute(
        """
        UPDATE carrinho_itens AS i
           SET variacao_tamanho_id = CASE WHEN v.tipo = 'tamanho' THEN v.id END,
               variacao_cor_id     = CASE WHEN v.tipo = 'cor'     THEN v.id END
          FROM produto_variacoes AS v
         WHERE v.id = i.variacao_id
        """
    )

    op.execute(
        "ALTER TABLE carrinho_itens "
        "ADD CONSTRAINT ck_carrinho_itens_variacao_tamanho_tipo "
        "CHECK (variacao_tamanho_tipo = 'tamanho'), "
        "ADD CONSTRAINT ck_carrinho_itens_variacao_cor_tipo "
        "CHECK (variacao_cor_tipo = 'cor')"
    )
    op.execute(
        "ALTER TABLE carrinho_itens "
        "ADD CONSTRAINT fk_carrinho_itens_variacao_tamanho_produto_variacoes "
        "FOREIGN KEY (variacao_tamanho_id, variacao_tamanho_tipo) "
        "REFERENCES produto_variacoes (id, tipo) "
        "ON DELETE SET NULL (variacao_tamanho_id), "
        "ADD CONSTRAINT fk_carrinho_itens_variacao_cor_produto_variacoes "
        "FOREIGN KEY (variacao_cor_id, variacao_cor_tipo) "
        "REFERENCES produto_variacoes (id, tipo) "
        "ON DELETE SET NULL (variacao_cor_id)"
    )

    # A unicidade do item passa a ser o CONJUNTO. NULLS NOT DISTINCT continua
    # sendo o que impede "produto sem variação nenhuma" de entrar duas vezes —
    # agora com dois NULLs em jogo em vez de um.
    op.execute(
        "ALTER TABLE carrinho_itens "
        "DROP CONSTRAINT uq_carrinho_itens_carrinho_produto_variacao"
    )
    op.execute(
        "ALTER TABLE carrinho_itens "
        "ADD CONSTRAINT uq_carrinho_itens_carrinho_produto_variacoes "
        "UNIQUE NULLS NOT DISTINCT "
        "(carrinho_id, produto_id, variacao_tamanho_id, variacao_cor_id)"
    )

    # Índice de apoio à FK: sem ele, apagar uma variação varre carrinho_itens.
    op.execute(
        "CREATE INDEX ix_carrinho_itens_variacao_tamanho ON carrinho_itens (variacao_tamanho_id)"
    )
    op.execute(
        "CREATE INDEX ix_carrinho_itens_variacao_cor ON carrinho_itens (variacao_cor_id)"
    )

    # A FK antiga, o índice ix_carrinho_itens_variacao e a CHECK de quantidade
    # caem junto com as colunas que os sustentam.
    op.drop_column("carrinho_itens", "variacao_id")
    op.drop_column("carrinho_itens", "quantidade")

    # ==================================================================
    # selecao_itens: congelar as DUAS variações
    # ==================================================================
    # Texto, não FK nem enum, igual às colunas que substituem: o histórico não
    # muda quando o catálogo muda.
    op.add_column("selecao_itens", sa.Column("variacao_tamanho", sa.String(60), nullable=True))
    op.add_column("selecao_itens", sa.Column("variacao_cor", sa.String(60), nullable=True))
    op.execute(
        """
        UPDATE selecao_itens
           SET variacao_tamanho = CASE WHEN variacao_tipo = 'tamanho' THEN variacao_valor END,
               variacao_cor     = CASE WHEN variacao_tipo = 'cor'     THEN variacao_valor END
         WHERE variacao_tipo IS NOT NULL
        """
    )
    op.drop_column("selecao_itens", "variacao_tipo")
    op.drop_column("selecao_itens", "variacao_valor")
    op.drop_column("selecao_itens", "quantidade")


def downgrade() -> None:
    # ==================================================================
    # selecao_itens
    # ==================================================================
    op.add_column("selecao_itens", sa.Column("variacao_tipo", sa.String(20), nullable=True))
    op.add_column("selecao_itens", sa.Column("variacao_valor", sa.String(60), nullable=True))
    op.execute(
        """
        UPDATE selecao_itens
           SET variacao_tipo  = CASE
                                  WHEN variacao_tamanho IS NOT NULL THEN 'tamanho'
                                  WHEN variacao_cor IS NOT NULL THEN 'cor'
                                END,
               variacao_valor = COALESCE(variacao_tamanho, variacao_cor)
        """
    )
    # PERDA DE DADO ACEITA: item congelado com tamanho E cor volta só com o
    # tamanho. Uma coluna não guarda dois valores.
    op.drop_column("selecao_itens", "variacao_tamanho")
    op.drop_column("selecao_itens", "variacao_cor")
    op.execute(
        "ALTER TABLE selecao_itens "
        "ADD COLUMN quantidade smallint NOT NULL DEFAULT 1, "
        "ADD CONSTRAINT ck_selecao_itens_quantidade_positiva CHECK (quantidade > 0)"
    )

    # ==================================================================
    # carrinho_itens
    # ==================================================================
    op.add_column("carrinho_itens", sa.Column("variacao_id", sa.Integer(), nullable=True))
    op.execute(
        "UPDATE carrinho_itens "
        "SET variacao_id = COALESCE(variacao_tamanho_id, variacao_cor_id)"
    )

    # PERDA DE DADO ACEITA: item com tamanho E cor volta só com o tamanho, e
    # dois itens do mesmo produto podem passar a colidir no UNIQUE antigo
    # (ex.: "M / Preto" e "M" viram os dois "M"). Fica o mais antigo — a mesma
    # regra que o serviço aplica quando uma troca de variação colide.
    op.execute(
        """
        DELETE FROM carrinho_itens AS i
         USING carrinho_itens AS anterior
         WHERE i.carrinho_id = anterior.carrinho_id
           AND i.produto_id = anterior.produto_id
           AND i.variacao_id IS NOT DISTINCT FROM anterior.variacao_id
           AND i.id > anterior.id
        """
    )

    op.execute(
        "ALTER TABLE carrinho_itens "
        "ADD CONSTRAINT fk_carrinho_itens_variacao_id_produto_variacoes "
        "FOREIGN KEY (variacao_id) REFERENCES produto_variacoes (id) ON DELETE SET NULL"
    )
    op.execute(
        "ALTER TABLE carrinho_itens "
        "DROP CONSTRAINT uq_carrinho_itens_carrinho_produto_variacoes"
    )
    op.execute(
        "ALTER TABLE carrinho_itens ADD CONSTRAINT uq_carrinho_itens_carrinho_produto_variacao "
        "UNIQUE NULLS NOT DISTINCT (carrinho_id, produto_id, variacao_id)"
    )
    op.execute("CREATE INDEX ix_carrinho_itens_variacao ON carrinho_itens (variacao_id)")

    op.drop_column("carrinho_itens", "variacao_tamanho_id")
    op.drop_column("carrinho_itens", "variacao_cor_id")
    op.drop_column("carrinho_itens", "variacao_tamanho_tipo")
    op.drop_column("carrinho_itens", "variacao_cor_tipo")

    op.execute(
        "ALTER TABLE carrinho_itens "
        "ADD COLUMN quantidade smallint NOT NULL DEFAULT 1, "
        "ADD CONSTRAINT ck_carrinho_itens_quantidade_positiva CHECK (quantidade > 0)"
    )

    op.execute("ALTER TABLE produto_variacoes DROP CONSTRAINT uq_produto_variacoes_id_tipo")
