"""Feminino e Masculino viram atributo do produto; categorias deixam de ter coleção.

Decisão de 30/09/2026 (caminho 1 do pedido "categorias livres"):

- `produtos` ganha `feminino` e `masculino` (as duas ao mesmo tempo = unissex) e perde
  `colecao_id`. `/feminino` e `/masculino` continuam filtrando, agora por esses campos.
- `categorias` perde `colecao_id`; o slug passa a ser único na tabela toda. As categorias
  que existiam uma vez em cada coleção ("Bolsas" no Feminino e no Masculino) são FUNDIDAS
  em uma só: fica a de menor id, e produtos e destinos adicionais são religados a ela.
- A tabela `colecoes` some. As duas coleções passam a ser constantes no código.

O downgrade é de melhor esforço: recria a tabela e as colunas, põe todas as categorias no
Feminino e desdobra no Masculino as que têm produto masculino. Para voltar de verdade,
restaure o dump feito antes da 0015.

Revisão: 0015_genero_no_produto
Anterior: 0014_loja_sempre_fechada
"""

from alembic import op
import sqlalchemy as sa

revision = "0015_genero_no_produto"
down_revision = "0014_loja_sempre_fechada"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Os dois campos de público, preenchidos a partir da coleção do produto e das
    #    categorias adicionais (o "segundo destino" da 0011 é o unissex de hoje).
    op.add_column("produtos", sa.Column("feminino", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("produtos", sa.Column("masculino", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute(
        """
        UPDATE produtos p SET
            feminino = EXISTS (
                SELECT 1 FROM colecoes c WHERE c.id = p.colecao_id AND c.slug = 'feminino'
            ) OR EXISTS (
                SELECT 1 FROM produto_categorias_adicionais a
                JOIN categorias ca ON ca.id = a.categoria_id
                JOIN colecoes c ON c.id = ca.colecao_id
                WHERE a.produto_id = p.id AND c.slug = 'feminino'
            ),
            masculino = EXISTS (
                SELECT 1 FROM colecoes c WHERE c.id = p.colecao_id AND c.slug = 'masculino'
            ) OR EXISTS (
                SELECT 1 FROM produto_categorias_adicionais a
                JOIN categorias ca ON ca.id = a.categoria_id
                JOIN colecoes c ON c.id = ca.colecao_id
                WHERE a.produto_id = p.id AND c.slug = 'masculino'
            )
        """
    )

    # 2. Solta a FK composta: a fusão abaixo religa produtos a categorias de OUTRA coleção.
    op.drop_constraint("fk_produtos_categoria_colecao_categorias", "produtos", type_="foreignkey")
    op.execute("DROP INDEX IF EXISTS ix_produtos_colecao_recentes")
    op.execute("DROP INDEX IF EXISTS ix_produtos_colecao_nome")

    # 3. Fusão das categorias de mesmo slug: a de menor id fica.
    op.execute(
        """
        CREATE TEMP TABLE fusao_categorias ON COMMIT DROP AS
        SELECT id AS de, MIN(id) OVER (PARTITION BY slug) AS para
        FROM categorias
        """
    )
    op.execute("DELETE FROM fusao_categorias WHERE de = para")
    op.execute("UPDATE produtos p SET categoria_id = f.para FROM fusao_categorias f WHERE p.categoria_id = f.de")
    op.execute(
        "UPDATE produto_categorias_adicionais a SET categoria_id = f.para "
        "FROM fusao_categorias f WHERE a.categoria_id = f.de "
        "AND NOT EXISTS (SELECT 1 FROM produto_categorias_adicionais x "
        "WHERE x.produto_id = a.produto_id AND x.categoria_id = f.para)"
    )
    # O que sobrou apontando para categoria fundida é duplicata, e a principal não se repete
    # como adicional.
    op.execute("DELETE FROM produto_categorias_adicionais WHERE categoria_id IN (SELECT de FROM fusao_categorias)")
    op.execute(
        "DELETE FROM produto_categorias_adicionais a USING produtos p "
        "WHERE a.produto_id = p.id AND a.categoria_id = p.categoria_id"
    )
    # A categoria que fica herda destaque, imagem e situação do grupo: se alguma das
    # duplicadas estava em destaque, aparecendo ou com foto, a fundida também está.
    op.execute(
        """
        UPDATE categorias k SET
            ativa = k.ativa OR COALESCE(g.alguma_ativa, false),
            imagem_url = COALESCE(k.imagem_url, g.imagem),
            destaque = k.destaque OR COALESCE(g.algum_destaque, false),
            destaque_ordem = CASE
                WHEN k.destaque_ordem IS NOT NULL THEN k.destaque_ordem
                WHEN g.algum_destaque THEN g.ordem_destaque
                ELSE NULL END
        FROM (
            SELECT f.para,
                   bool_or(c.ativa) AS alguma_ativa,
                   max(c.imagem_url) AS imagem,
                   bool_or(c.destaque) AS algum_destaque,
                   min(c.destaque_ordem) AS ordem_destaque
            FROM fusao_categorias f JOIN categorias c ON c.id = f.de
            GROUP BY f.para
        ) g
        WHERE k.id = g.para
        """
    )
    op.execute("DELETE FROM categorias WHERE id IN (SELECT de FROM fusao_categorias)")

    # 4. Tira a coleção das categorias e dos produtos.
    op.drop_constraint("uq_categorias_colecao_slug", "categorias", type_="unique")
    op.drop_constraint("uq_categorias_id_colecao", "categorias", type_="unique")
    op.drop_constraint("fk_categorias_colecao_id_colecoes", "categorias", type_="foreignkey")
    op.drop_column("categorias", "colecao_id")
    op.drop_column("produtos", "colecao_id")
    op.create_unique_constraint("uq_categorias_slug", "categorias", ["slug"])
    op.create_foreign_key(
        "fk_produtos_categoria_id_categorias", "produtos", "categorias",
        ["categoria_id"], ["id"], ondelete="RESTRICT",
    )

    # 5. Pelo menos um público, e os índices das páginas /feminino e /masculino.
    op.create_check_constraint("ck_produtos_publico", "produtos", "feminino OR masculino")
    op.alter_column("produtos", "feminino", server_default=None)
    op.alter_column("produtos", "masculino", server_default=None)
    for lado in ("feminino", "masculino"):
        op.execute(
            f"CREATE INDEX ix_produtos_{lado}_recentes ON produtos (criado_em DESC, id DESC) "
            f"WHERE {lado} AND status <> 'oculto'"
        )
        op.execute(
            f'CREATE INDEX ix_produtos_{lado}_nome ON produtos ((nome_ordenacao COLLATE "C"), id) '
            f"WHERE {lado} AND status <> 'oculto'"
        )

    # 6. A tabela de coleções deixa de existir.
    op.drop_table("colecoes")


def downgrade() -> None:
    op.create_table(
        "colecoes",
        sa.Column("id", sa.SmallInteger(), sa.Identity(), nullable=False),
        sa.Column("nome", sa.String(40), nullable=False),
        sa.Column("slug", sa.String(40), nullable=False),
        sa.Column("ordem", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("ativa", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("criado_em", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("atualizado_em", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_colecoes"),
        sa.UniqueConstraint("slug", name="uq_colecoes_slug"),
    )
    op.execute(
        "INSERT INTO colecoes (nome, slug, ordem) VALUES "
        "('Feminina', 'feminino', 1), ('Masculina', 'masculino', 2)"
    )

    for lado in ("feminino", "masculino"):
        op.execute(f"DROP INDEX IF EXISTS ix_produtos_{lado}_recentes")
        op.execute(f"DROP INDEX IF EXISTS ix_produtos_{lado}_nome")
    op.drop_constraint("ck_produtos_publico", "produtos", type_="check")
    op.drop_constraint("uq_categorias_slug", "categorias", type_="unique")
    op.drop_constraint("fk_produtos_categoria_id_categorias", "produtos", type_="foreignkey")

    op.add_column("categorias", sa.Column("colecao_id", sa.SmallInteger(), nullable=True))
    op.add_column("produtos", sa.Column("colecao_id", sa.SmallInteger(), nullable=True))
    op.execute("UPDATE categorias SET colecao_id = (SELECT id FROM colecoes WHERE slug = 'feminino')")
    op.execute(
        "UPDATE produtos SET colecao_id = (SELECT id FROM colecoes WHERE slug = "
        "CASE WHEN feminino THEN 'feminino' ELSE 'masculino' END)"
    )

    # Toda categoria usada por produto masculino ganha uma cópia no Masculino.
    op.execute(
        """
        CREATE TEMP TABLE copias_categorias ON COMMIT DROP AS
        SELECT c.id AS origem, nextval(pg_get_serial_sequence('categorias', 'id')) AS copia
        FROM categorias c
        WHERE EXISTS (SELECT 1 FROM produtos p WHERE p.categoria_id = c.id AND p.masculino)
        """
    )
    op.execute(
        """
        INSERT INTO categorias (id, colecao_id, nome, slug, imagem_url, destaque, destaque_ordem, ordem, ativa)
        OVERRIDING SYSTEM VALUE
        SELECT k.copia, (SELECT id FROM colecoes WHERE slug = 'masculino'), c.nome, c.slug,
               c.imagem_url, false, NULL, c.ordem, c.ativa
        FROM copias_categorias k JOIN categorias c ON c.id = k.origem
        """
    )
    # Unissex: a cópia do Masculino entra como categoria adicional (segundo destino da 0011).
    op.execute(
        "INSERT INTO produto_categorias_adicionais (produto_id, categoria_id) "
        "SELECT p.id, k.copia FROM produtos p JOIN copias_categorias k ON k.origem = p.categoria_id "
        "WHERE p.feminino AND p.masculino ON CONFLICT DO NOTHING"
    )
    # Só masculino: a principal passa para a cópia e a coleção do produto vira Masculino.
    op.execute(
        "UPDATE produtos p SET categoria_id = k.copia, colecao_id = "
        "(SELECT id FROM colecoes WHERE slug = 'masculino') "
        "FROM copias_categorias k WHERE p.categoria_id = k.origem AND NOT p.feminino"
    )

    op.alter_column("categorias", "colecao_id", nullable=False)
    op.alter_column("produtos", "colecao_id", nullable=False)
    op.create_unique_constraint("uq_categorias_colecao_slug", "categorias", ["colecao_id", "slug"])
    op.create_unique_constraint("uq_categorias_id_colecao", "categorias", ["id", "colecao_id"])
    op.create_foreign_key(
        "fk_categorias_colecao_id_colecoes", "categorias", "colecoes", ["colecao_id"], ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_produtos_categoria_colecao_categorias", "produtos", "categorias",
        ["categoria_id", "colecao_id"], ["id", "colecao_id"], ondelete="RESTRICT",
    )
    op.execute(
        "CREATE INDEX ix_produtos_colecao_recentes ON produtos (colecao_id, criado_em DESC, id DESC) "
        "WHERE status <> 'oculto'"
    )
    op.execute(
        'CREATE INDEX ix_produtos_colecao_nome ON produtos (colecao_id, (nome_ordenacao COLLATE "C"), id) '
        "WHERE status <> 'oculto'"
    )
    op.drop_column("produtos", "feminino")
    op.drop_column("produtos", "masculino")
