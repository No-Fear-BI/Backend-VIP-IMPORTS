"""Cor vira vocabulário: tabela `cores` e ligação das variações de cor.

O PROBLEMA QUE ESTA REVISÃO RESOLVE. Até aqui, cor era texto livre dentro de
`produto_variacoes` (`tipo='cor'`, `valor='Preto'`). Isso basta para mostrar a
peça, mas não sustenta as duas coisas que o painel precisa: dono cadastrando a
paleta da loja e cliente filtrando a vitrine por cor. Com texto livre, "Preto",
"preto" e "PRETO" são três cores diferentes para o banco, e um filtro `?cor=`
em cima de `valor` devolveria um terço dos produtos sem ninguém perceber o
buraco. A partir daqui, cor é linha em `cores`, e a variação aponta para ela.

O QUE **NÃO** MUDA, de propósito:

1. `produto_variacoes.valor` continua sendo o texto exibido, e esta migração
   NÃO o reescreve. A tentação é normalizar tudo para o nome da cor ("preto"
   viraria "Preto"), mas um produto que tenha as duas grafias como variações
   separadas colidiria em `uq_produto_variacoes_produto_tipo_valor`, e a saída
   seria apagar uma das linhas — que é justamente a que pode estar escolhida
   no carrinho de alguém (`carrinho_itens.variacao_cor_id`). Trocar a grafia
   histórica de quem já escolheu não vale o ganho estético. As grades salvas
   pelo painel a partir de agora já nascem com o nome do vocabulário, e o
   filtro nunca depende de `valor`: ele lê `cor_id`.
2. A UNIQUE `(id, tipo)` e a FK composta de `carrinho_itens` (revisão 0005)
   ficam como estão. Esta revisão não toca no caminho do carrinho.

O BACKFILL RODA EM PYTHON, e não em SQL, porque o slug precisa da mesma
normalização sem acento do resto do projeto e `unaccent()` não está instalado
— decisão da 0001, por não ser IMMUTABLE (modelagem, 5.1). A regra vai copiada
aqui dentro, congelada, em vez de importada de `vip_api.texto`: migração que
importa código de aplicação passa a depender de uma função que alguém vai
mudar daqui a um ano, e o histórico deixa de ser reproduzível.

Grafias que normalizam para o mesmo slug viram UMA cor só ("Preto", "preto" e
"PRETO" = `preto`). O nome que fica é a grafia mais usada no catálogo, com
empate resolvido em ordem alfabética — determinístico, para o resultado não
depender da ordem em que o PostgreSQL devolveu as linhas.

A CHECK entra no fim, depois do backfill, pelo mesmo motivo da 0006: criada
antes, a primeira variação de cor sem `cor_id` derrubaria a migração.

Revisão: 0007
Anterior: 0006
"""

import unicodedata
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import TIMESTAMP

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Cópia congelada de vip_api.texto.gerar_slug (ver docstring).
def _gerar_slug(texto: str) -> str:
    decomposto = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in decomposto if not unicodedata.combining(c))
    base = sem_acento.lower().strip()
    palavras = "".join(c if c.isalnum() else " " for c in base).split()
    return "-".join(palavras)


def _backfill(conexao) -> None:
    """Uma cor por slug, a partir das grafias já gravadas."""
    linhas = conexao.execute(
        sa.text(
            "SELECT valor, count(*) AS usos FROM produto_variacoes "
            "WHERE tipo = 'cor' GROUP BY valor"
        )
    ).all()
    if not linhas:
        return

    # slug -> {grafia: usos}. O dicionário agrupa o que o banco enxerga como
    # valores distintos mas que são a mesma cor.
    por_slug: dict[str, dict[str, int]] = {}
    for valor, usos in linhas:
        slug = _gerar_slug(valor)
        if not slug:
            # Variação de cor com valor só de pontuação não vira cor nenhuma;
            # fica com cor_id nulo e a CHECK mais abaixo recusaria. É dado
            # quebrado, então some junto com a restrição — avisa em vez de
            # silenciar.
            raise RuntimeError(
                f"Variação de cor com valor sem letra nem número: {valor!r}. "
                "Corrija a linha antes de migrar."
            )
        por_slug.setdefault(slug, {})[valor] = usos

    for slug, grafias in sorted(por_slug.items()):
        # Grafia mais usada; empate pela ordem alfabética, para o resultado
        # não depender da ordem das linhas.
        nome = sorted(grafias.items(), key=lambda par: (-par[1], par[0]))[0][0].strip()
        cor_id = conexao.execute(
            sa.text("INSERT INTO cores (nome, slug) VALUES (:nome, :slug) RETURNING id"),
            {"nome": nome, "slug": slug},
        ).scalar_one()
        conexao.execute(
            sa.text(
                "UPDATE produto_variacoes SET cor_id = :cor_id "
                "WHERE tipo = 'cor' AND valor = ANY(:grafias)"
            ),
            {"cor_id": cor_id, "grafias": list(grafias)},
        )


def upgrade() -> None:
    op.create_table(
        "cores",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column("nome", sa.String(length=60), nullable=False),
        sa.Column("slug", sa.String(length=60), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ativa", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "criado_em", TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "atualizado_em",
            TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("slug", name="uq_cores_slug"),
    )

    op.add_column("produto_variacoes", sa.Column("cor_id", sa.Integer(), nullable=True))
    # RESTRICT e não CASCADE: apagar uma cor que está em produto tem que doer
    # e voltar 409 com a contagem, como em marca. CASCADE aqui apagaria a
    # variação — e com ela a escolha de quem tem a peça no carrinho.
    op.create_foreign_key(
        "fk_produto_variacoes_cor_id_cores",
        "produto_variacoes",
        "cores",
        ["cor_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    _backfill(op.get_bind())

    # O filtro `?cor=` é um EXISTS por produto: (cor_id, produto_id) é a ordem
    # que serve a ele, não a inversa.
    op.create_index(
        "ix_produto_variacoes_cor", "produto_variacoes", ["cor_id", "produto_id"]
    )
    # Tamanho nunca tem cor_id; cor sempre tem. Sem isso, uma grade salva pela
    # metade deixaria cor solta do vocabulário e o filtro perderia o produto.
    op.create_check_constraint(
        "ck_produto_variacoes_cor_id",
        "produto_variacoes",
        "(tipo = 'cor'::variacao_tipo) = (cor_id IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_produto_variacoes_cor_id", "produto_variacoes", type_="check")
    op.drop_index("ix_produto_variacoes_cor", table_name="produto_variacoes")
    op.drop_constraint(
        "fk_produto_variacoes_cor_id_cores", "produto_variacoes", type_="foreignkey"
    )
    op.drop_column("produto_variacoes", "cor_id")
    op.drop_table("cores")
