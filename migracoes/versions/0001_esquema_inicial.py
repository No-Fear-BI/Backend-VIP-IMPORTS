"""Esquema inicial: catálogo, cliente, carrinho, seleção, administração e o
controle de acesso congelado (seção 05 do contrato).

Uma única revisão com o schema inteiro do docs/modelagem-banco.md revisado.
Não dividida por fatia de propósito — um dev em uma semana, remodelar três
vezes é o desperdício mais caro disponível.

Revisão: 0001
Anterior: nenhuma
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Os quatro tipos enumerados do desenho (docs/modelagem-banco.md, seção 3).
# variacao_tipo fechado em dois valores: numeração de calçado/anel entra como
# VALOR de "tamanho", não como um terceiro tipo (decisão fechada, seção 7).
PRODUTO_STATUS = postgresql.ENUM(
    "normal", "esgotado", "oculto", name="produto_status", create_type=False
)
ACESSO_MODO = postgresql.ENUM(
    "aberto", "senha_compartilhada", "aprovacao", name="acesso_modo", create_type=False
)
ACESSO_SITUACAO = postgresql.ENUM(
    "pendente", "aprovado", "recusado", name="acesso_situacao", create_type=False
)
VARIACAO_TIPO = postgresql.ENUM(
    "tamanho", "cor", name="variacao_tipo", create_type=False
)


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Extensões. unaccent NÃO entra — normalização de texto é feita pela
    # aplicação, nunca por coluna gerada no banco (docs/modelagem-banco.md,
    # seção 5.1 — unaccent() não é IMMUTABLE, e mentir sobre isso para o
    # PostgreSQL corrompe índice em silêncio se o dicionário mudar).
    # ------------------------------------------------------------------
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # ------------------------------------------------------------------
    # Tipos enumerados — antes de qualquer tabela que os use.
    # ------------------------------------------------------------------
    op.execute("CREATE TYPE produto_status AS ENUM ('normal', 'esgotado', 'oculto')")
    op.execute(
        "CREATE TYPE acesso_modo AS ENUM ('aberto', 'senha_compartilhada', 'aprovacao')"
    )
    op.execute(
        "CREATE TYPE acesso_situacao AS ENUM ('pendente', 'aprovado', 'recusado')"
    )
    op.execute("CREATE TYPE variacao_tipo AS ENUM ('tamanho', 'cor')")

    # ==================================================================
    # CATÁLOGO
    # ==================================================================

    op.create_table(
        "colecoes",
        sa.Column("id", sa.SmallInteger(), sa.Identity(), nullable=False),
        sa.Column("nome", sa.String(40), nullable=False),
        sa.Column("slug", sa.String(40), nullable=False),
        sa.Column("ordem", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("ativa", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "criado_em", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "atualizado_em", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id", name="pk_colecoes"),
        sa.UniqueConstraint("slug", name="uq_colecoes_slug"),
    )

    op.create_table(
        "marcas",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("nome", sa.String(80), nullable=False),
        sa.Column("nome_busca", sa.Text(), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("logo_url", sa.Text(), nullable=True),
        sa.Column("ordem", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ativa", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "criado_em", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "atualizado_em", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id", name="pk_marcas"),
        sa.UniqueConstraint("slug", name="uq_marcas_slug"),
    )

    op.create_table(
        "categorias",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("colecao_id", sa.SmallInteger(), nullable=False),
        sa.Column("nome", sa.String(80), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("imagem_url", sa.Text(), nullable=True),
        sa.Column("destaque", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("destaque_ordem", sa.Integer(), nullable=True),
        sa.Column("ordem", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ativa", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "criado_em", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "atualizado_em", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id", name="pk_categorias"),
        # Unicidade composta — regra 3 da tarefa 1: slug é único POR COLEÇÃO,
        # não global. "bolsas" existe em Feminino e em Masculino.
        sa.UniqueConstraint("colecao_id", "slug", name="uq_categorias_colecao_slug"),
        # Alvo da FK composta de produtos (evita coleção dessincronizada).
        sa.UniqueConstraint("id", "colecao_id", name="uq_categorias_id_colecao"),
        sa.ForeignKeyConstraint(
            ["colecao_id"], ["colecoes.id"], name="fk_categorias_colecao_id_colecoes", ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "destaque = false OR destaque_ordem IS NOT NULL",
            name="ck_categorias_destaque_ordem",
        ),
    )

    op.create_table(
        "produtos",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("codigo", sa.String(32), nullable=False),
        # Rastreabilidade da origem — nuláveis, sem restrição (decisão fechada,
        # seção 7): codigo é gerado pela No Fear, codigo_origem/origem_url
        # servem à deduplicação da tarefa 72 e podem mudar de formato quando
        # a tarefa 38 rodar (pendência externa, seção 8).
        sa.Column("codigo_origem", sa.String(80), nullable=True),
        sa.Column("origem_url", sa.Text(), nullable=True),
        sa.Column("nome", sa.String(180), nullable=False),
        # Preenchida pela aplicação — nunca coluna gerada (unaccent() não é
        # IMMUTABLE; ver docs/modelagem-banco.md, seção 5.1).
        sa.Column("nome_ordenacao", sa.Text(), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("status", PRODUTO_STATUS, nullable=False, server_default="normal"),
        sa.Column("destaque", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("destaque_ordem", sa.Integer(), nullable=True),
        sa.Column("marca_id", sa.Integer(), nullable=False),
        sa.Column("categoria_id", sa.Integer(), nullable=False),
        # Duplicado de propósito em relação à coleção da categoria — travado
        # pela FK composta abaixo, nunca pode dessincronizar.
        sa.Column("colecao_id", sa.SmallInteger(), nullable=False),
        sa.Column(
            "criado_em", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "atualizado_em", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id", name="pk_produtos"),
        sa.UniqueConstraint("codigo", name="uq_produtos_codigo"),
        sa.ForeignKeyConstraint(
            ["marca_id"], ["marcas.id"], name="fk_produtos_marca_id_marcas", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["categoria_id", "colecao_id"],
            ["categorias.id", "categorias.colecao_id"],
            name="fk_produtos_categoria_colecao_categorias",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "destaque = false OR destaque_ordem IS NOT NULL",
            name="ck_produtos_destaque_ordem",
        ),
    )

    op.create_table(
        "produto_imagens",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("produto_id", sa.Integer(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("alt", sa.String(200), nullable=True),
        sa.Column("ordem", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("capa", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "criado_em", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id", name="pk_produto_imagens"),
        sa.ForeignKeyConstraint(
            ["produto_id"], ["produtos.id"], name="fk_produto_imagens_produto_id_produtos", ondelete="CASCADE"
        ),
        # DEFERRABLE: o endpoint de reordenar manda a lista inteira e passa
        # por um instante com ordens duplicadas dentro da mesma transação.
        sa.UniqueConstraint(
            "produto_id",
            "ordem",
            name="uq_produto_imagens_produto_ordem",
            deferrable=True,
            initially="DEFERRED",
        ),
    )

    op.create_table(
        "produto_variacoes",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("produto_id", sa.Integer(), nullable=False),
        sa.Column("tipo", VARIACAO_TIPO, nullable=False),
        sa.Column("valor", sa.String(60), nullable=False),
        sa.Column("disponivel", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("ordem", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "criado_em", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "atualizado_em", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id", name="pk_produto_variacoes"),
        sa.ForeignKeyConstraint(
            ["produto_id"], ["produtos.id"], name="fk_produto_variacoes_produto_id_produtos", ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "produto_id", "tipo", "valor", name="uq_produto_variacoes_produto_tipo_valor"
        ),
    )

    op.create_table(
        "banners",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("titulo", sa.String(120), nullable=True),
        sa.Column("subtitulo", sa.String(200), nullable=True),
        sa.Column("imagem_url", sa.Text(), nullable=False),
        sa.Column("imagem_url_mobile", sa.Text(), nullable=True),
        sa.Column("alt", sa.String(200), nullable=True),
        sa.Column("link_url", sa.Text(), nullable=True),
        sa.Column("ordem", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "criado_em", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "atualizado_em", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id", name="pk_banners"),
    )

    # ==================================================================
    # CLIENTE
    # ==================================================================

    op.create_table(
        "clientes",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("nome", sa.String(120), nullable=True),
        sa.Column("telefone", sa.String(20), nullable=True),
        sa.Column("acesso_status", ACESSO_SITUACAO, nullable=False, server_default="aprovado"),
        sa.Column("ultimo_acesso_em", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "criado_em", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "atualizado_em", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id", name="pk_clientes"),
        sa.UniqueConstraint("email", name="uq_clientes_email"),
    )

    op.create_table(
        "cliente_sessoes",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("cliente_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.CHAR(64), nullable=False),
        sa.Column(
            "criado_em", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        # 90 dias, renovada a cada uso — a renovação é feita pela aplicação
        # a cada requisição autenticada, este é só o valor na criação.
        sa.Column(
            "expira_em",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now() + interval '90 days'"),
        ),
        sa.Column("revogado_em", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_cliente_sessoes"),
        sa.UniqueConstraint("token_hash", name="uq_cliente_sessoes_token_hash"),
        sa.ForeignKeyConstraint(
            ["cliente_id"], ["clientes.id"], name="fk_cliente_sessoes_cliente_id_clientes", ondelete="CASCADE"
        ),
    )

    # ==================================================================
    # SELEÇÃO EM ANDAMENTO (dado vivo)
    # ==================================================================

    op.create_table(
        "favoritos",
        sa.Column("cliente_id", sa.Integer(), nullable=False),
        sa.Column("produto_id", sa.Integer(), nullable=False),
        sa.Column(
            "criado_em", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("cliente_id", "produto_id", name="pk_favoritos"),
        sa.ForeignKeyConstraint(
            ["cliente_id"], ["clientes.id"], name="fk_favoritos_cliente_id_clientes", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["produto_id"], ["produtos.id"], name="fk_favoritos_produto_id_produtos", ondelete="CASCADE"
        ),
    )

    op.create_table(
        "carrinhos",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("cliente_id", sa.Integer(), nullable=True),
        sa.Column("visitante_token_hash", sa.CHAR(64), nullable=True),
        sa.Column(
            "criado_em", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "atualizado_em", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id", name="pk_carrinhos"),
        sa.UniqueConstraint("visitante_token_hash", name="uq_carrinhos_visitante_token_hash"),
        sa.ForeignKeyConstraint(
            ["cliente_id"], ["clientes.id"], name="fk_carrinhos_cliente_id_clientes", ondelete="CASCADE"
        ),
        sa.CheckConstraint(
            "cliente_id IS NOT NULL OR visitante_token_hash IS NOT NULL",
            name="ck_carrinhos_cliente_ou_visitante",
        ),
    )

    op.create_table(
        "carrinho_itens",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("carrinho_id", sa.Integer(), nullable=False),
        sa.Column("produto_id", sa.Integer(), nullable=False),
        sa.Column("variacao_id", sa.Integer(), nullable=True),
        sa.Column("quantidade", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("observacao", sa.String(280), nullable=True),
        sa.Column(
            "criado_em", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "atualizado_em", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id", name="pk_carrinho_itens"),
        sa.ForeignKeyConstraint(
            ["carrinho_id"], ["carrinhos.id"], name="fk_carrinho_itens_carrinho_id_carrinhos", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["produto_id"], ["produtos.id"], name="fk_carrinho_itens_produto_id_produtos", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["variacao_id"],
            ["produto_variacoes.id"],
            name="fk_carrinho_itens_variacao_id_produto_variacoes",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint("quantidade > 0", name="ck_carrinho_itens_quantidade_positiva"),
    )
    # UNIQUE NULLS NOT DISTINCT: "produto sem variação" não pode ser
    # adicionado duas vezes — por padrão o PostgreSQL trata dois NULL como
    # diferentes, essa cláusula fecha a brecha. Fora do create_table porque
    # é sintaxe específica do PostgreSQL 15+, mais clara em SQL direto.
    op.execute(
        "ALTER TABLE carrinho_itens ADD CONSTRAINT uq_carrinho_itens_carrinho_produto_variacao "
        "UNIQUE NULLS NOT DISTINCT (carrinho_id, produto_id, variacao_id)"
    )

    # ==================================================================
    # SELEÇÃO ENVIADA (dado congelado — regra 4 da tarefa 1)
    # ==================================================================

    op.create_table(
        "selecoes",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("cliente_id", sa.Integer(), nullable=True),
        sa.Column("cliente_nome", sa.String(120), nullable=True),
        sa.Column("cliente_email", postgresql.CITEXT(), nullable=False),
        sa.Column("cliente_telefone", sa.String(20), nullable=True),
        sa.Column("observacao", sa.Text(), nullable=True),
        sa.Column("total_itens", sa.SmallInteger(), nullable=False),
        sa.Column(
            "criado_em", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id", name="pk_selecoes"),
        # Nulável e SEM cascata: cliente apagado não leva o histórico junto.
        sa.ForeignKeyConstraint(
            ["cliente_id"], ["clientes.id"], name="fk_selecoes_cliente_id_clientes", ondelete="SET NULL"
        ),
        sa.CheckConstraint("total_itens >= 0", name="ck_selecoes_total_itens"),
    )

    op.create_table(
        "selecao_itens",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("selecao_id", sa.Integer(), nullable=False),
        sa.Column("produto_id", sa.Integer(), nullable=True),
        # Tudo abaixo é CONGELADO: cópia em texto do que o cliente viu no
        # momento do envio. variacao_tipo aqui é varchar, NÃO o enum —
        # se o enum mudar depois, o histórico não muda junto (regra 4).
        sa.Column("produto_codigo", sa.String(32), nullable=False),
        sa.Column("produto_nome", sa.String(180), nullable=False),
        sa.Column("marca_nome", sa.String(80), nullable=False),
        sa.Column("categoria_nome", sa.String(80), nullable=False),
        sa.Column("colecao_nome", sa.String(40), nullable=False),
        sa.Column("imagem_url", sa.Text(), nullable=True),
        sa.Column("variacao_tipo", sa.String(20), nullable=True),
        sa.Column("variacao_valor", sa.String(60), nullable=True),
        sa.Column("quantidade", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("observacao", sa.String(280), nullable=True),
        sa.Column("ordem", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "criado_em", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id", name="pk_selecao_itens"),
        sa.ForeignKeyConstraint(
            ["selecao_id"], ["selecoes.id"], name="fk_selecao_itens_selecao_id_selecoes", ondelete="CASCADE"
        ),
        # Nulável e SEM cascata: produto apagado deixa a linha intacta, só
        # perde o link. É exatamente a regra 4 da tarefa 1.
        sa.ForeignKeyConstraint(
            ["produto_id"], ["produtos.id"], name="fk_selecao_itens_produto_id_produtos", ondelete="SET NULL"
        ),
        sa.CheckConstraint("quantidade > 0", name="ck_selecao_itens_quantidade_positiva"),
    )

    # ==================================================================
    # ADMINISTRAÇÃO E CONTROLE DE ACESSO (seção 05 do contrato, congelado)
    # ==================================================================

    op.create_table(
        "administradores",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("nome", sa.String(120), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("senha_hash", sa.Text(), nullable=False),
        sa.Column(
            "senha_alterada_em", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("ultimo_login_em", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "criado_em", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "atualizado_em", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id", name="pk_administradores"),
        sa.UniqueConstraint("email", name="uq_administradores_email"),
    )

    op.create_table(
        "admin_sessoes",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("administrador_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.CHAR(64), nullable=False),
        sa.Column(
            "criado_em", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        # 12 horas, SEM renovação automática — ao contrário da sessão de
        # cliente, uso não estende o prazo.
        sa.Column(
            "expira_em",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now() + interval '12 hours'"),
        ),
        sa.Column("revogado_em", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_admin_sessoes"),
        sa.UniqueConstraint("token_hash", name="uq_admin_sessoes_token_hash"),
        sa.ForeignKeyConstraint(
            ["administrador_id"],
            ["administradores.id"],
            name="fk_admin_sessoes_administrador_id_administradores",
            ondelete="CASCADE",
        ),
    )

    op.create_table(
        "acesso_config",
        # Tabela de linha única: CHECK id = 1 torna impossível existir uma
        # segunda configuração. Modelado agora, sem rota ainda (regra 7 da
        # tarefa 1) — remodelar isto depois de 11 mil produtos e clientes
        # reais cadastrados é o cenário caro que este plano evita.
        sa.Column("id", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("modo", ACESSO_MODO, nullable=False, server_default="aberto"),
        sa.Column("senha_hash", sa.Text(), nullable=True),
        sa.Column("mensagem_bloqueio", sa.Text(), nullable=True),
        sa.Column("atualizado_por_admin_id", sa.Integer(), nullable=True),
        sa.Column(
            "atualizado_em", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id", name="pk_acesso_config"),
        sa.ForeignKeyConstraint(
            ["atualizado_por_admin_id"],
            ["administradores.id"],
            name="fk_acesso_config_atualizado_por_admin_id_administradores",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint("id = 1", name="ck_acesso_config_linha_unica"),
        sa.CheckConstraint(
            "modo <> 'senha_compartilhada' OR senha_hash IS NOT NULL",
            name="ck_acesso_config_senha_obrigatoria",
        ),
    )

    op.create_table(
        "acesso_solicitacoes",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("cliente_id", sa.Integer(), nullable=False),
        # Congelado, mesmo motivo da seleção: a fila precisa fazer sentido
        # mesmo se o cadastro do cliente mudar depois.
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("nome", sa.String(120), nullable=True),
        sa.Column("telefone", sa.String(20), nullable=True),
        sa.Column("situacao", ACESSO_SITUACAO, nullable=False, server_default="pendente"),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column("decidido_por_admin_id", sa.Integer(), nullable=True),
        sa.Column("decidido_em", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "criado_em", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id", name="pk_acesso_solicitacoes"),
        sa.ForeignKeyConstraint(
            ["cliente_id"], ["clientes.id"], name="fk_acesso_solicitacoes_cliente_id_clientes", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["decidido_por_admin_id"],
            ["administradores.id"],
            name="fk_acesso_solicitacoes_decidido_por_admin_id_administradores",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "(situacao = 'pendente') = (decidido_em IS NULL)",
            name="ck_acesso_solicitacoes_decisao",
        ),
    )

    # ==================================================================
    # ÍNDICES DE UNICIDADE PARCIAL
    # Não dá para expressar UNIQUE parcial como restrição de tabela no
    # PostgreSQL — só como índice com WHERE. Cada um é a integridade que a
    # seção 5.3 do documento descreve, não um extra de desempenho.
    # ==================================================================
    op.execute(
        "CREATE UNIQUE INDEX uq_produto_imagens_capa ON produto_imagens (produto_id) WHERE capa"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_carrinhos_cliente_ativo ON carrinhos (cliente_id) "
        "WHERE cliente_id IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_acesso_solicitacoes_pendente ON acesso_solicitacoes (cliente_id) "
        "WHERE situacao = 'pendente'"
    )

    # ==================================================================
    # ÍNDICES DE DESEMPENHO
    # Os 24 que sobraram da poda da tarefa 2 (docs/modelagem-banco.md,
    # seção 5.3) — cada um citando o endpoint que serve, lá no documento.
    # ==================================================================

    # --- produtos: catálogo público, filtros + paginação por cursor -----
    op.execute(
        "CREATE INDEX ix_produtos_pub_recentes ON produtos (criado_em DESC, id DESC) "
        "WHERE status <> 'oculto'"
    )
    op.execute(
        'CREATE INDEX ix_produtos_pub_nome ON produtos ((nome_ordenacao COLLATE "C"), id) '
        "WHERE status <> 'oculto'"
    )
    op.execute(
        "CREATE INDEX ix_produtos_marca_recentes ON produtos (marca_id, criado_em DESC, id DESC) "
        "WHERE status <> 'oculto'"
    )
    op.execute(
        'CREATE INDEX ix_produtos_marca_nome ON produtos (marca_id, (nome_ordenacao COLLATE "C"), id) '
        "WHERE status <> 'oculto'"
    )
    op.execute(
        "CREATE INDEX ix_produtos_categoria_recentes ON produtos (categoria_id, criado_em DESC, id DESC) "
        "WHERE status <> 'oculto'"
    )
    op.execute(
        'CREATE INDEX ix_produtos_categoria_nome ON produtos (categoria_id, (nome_ordenacao COLLATE "C"), id) '
        "WHERE status <> 'oculto'"
    )
    op.execute(
        "CREATE INDEX ix_produtos_colecao_recentes ON produtos (colecao_id, criado_em DESC, id DESC) "
        "WHERE status <> 'oculto'"
    )
    op.execute(
        'CREATE INDEX ix_produtos_colecao_nome ON produtos (colecao_id, (nome_ordenacao COLLATE "C"), id) '
        "WHERE status <> 'oculto'"
    )
    op.execute(
        "CREATE INDEX ix_produtos_destaque ON produtos (destaque_ordem, id) "
        "WHERE destaque AND status <> 'oculto'"
    )
    op.execute(
        "CREATE INDEX ix_produtos_admin ON produtos (status, criado_em DESC, id DESC)"
    )
    op.execute(
        "CREATE INDEX ix_produtos_relacionados ON produtos (categoria_id, marca_id, id) "
        "WHERE status <> 'oculto'"
    )
    op.execute(
        "CREATE INDEX ix_produtos_nome_trgm ON produtos USING gin (nome_ordenacao gin_trgm_ops)"
    )

    # --- marcas, categorias ---------------------------------------------
    op.execute(
        "CREATE INDEX ix_marcas_nome_trgm ON marcas USING gin (nome_busca gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_categorias_destaque ON categorias (destaque_ordem, id) WHERE destaque"
    )

    # --- banners ----------------------------------------------------------
    op.execute("CREATE INDEX ix_banners_ativos ON banners (ordem, id) WHERE ativo")

    # --- clientes -----------------------------------------------------
    op.execute(
        "CREATE INDEX ix_clientes_recentes ON clientes (criado_em DESC, id DESC)"
    )

    # --- favoritos, carrinho_itens: apoio de FK para exclusão de produto --
    op.execute(
        "CREATE INDEX ix_favoritos_cliente_recentes ON favoritos (cliente_id, criado_em DESC, produto_id DESC)"
    )
    op.execute("CREATE INDEX ix_favoritos_produto ON favoritos (produto_id)")
    op.execute("CREATE INDEX ix_carrinho_itens_produto ON carrinho_itens (produto_id)")
    op.execute("CREATE INDEX ix_carrinho_itens_variacao ON carrinho_itens (variacao_id)")

    # --- selecoes, selecao_itens ----------------------------------------
    op.execute(
        "CREATE INDEX ix_selecoes_recentes ON selecoes (criado_em DESC, id DESC)"
    )
    op.execute(
        "CREATE INDEX ix_selecoes_cliente ON selecoes (cliente_id, criado_em DESC)"
    )
    op.execute(
        "CREATE INDEX ix_selecao_itens_selecao ON selecao_itens (selecao_id, ordem, id)"
    )
    op.execute("CREATE INDEX ix_selecao_itens_produto ON selecao_itens (produto_id)")


def downgrade() -> None:
    # Ordem inversa da criação — respeita as FKs. Índices e restrições vão
    # junto com a tabela, não precisam de DROP separado.
    op.drop_table("acesso_solicitacoes")
    op.drop_table("acesso_config")
    op.drop_table("admin_sessoes")
    op.drop_table("administradores")
    op.drop_table("selecao_itens")
    op.drop_table("selecoes")
    op.drop_table("carrinho_itens")
    op.drop_table("carrinhos")
    op.drop_table("favoritos")
    op.drop_table("cliente_sessoes")
    op.drop_table("clientes")
    op.drop_table("banners")
    op.drop_table("produto_variacoes")
    op.drop_table("produto_imagens")
    op.drop_table("produtos")
    op.drop_table("categorias")
    op.drop_table("marcas")
    op.drop_table("colecoes")

    op.execute("DROP TYPE variacao_tipo")
    op.execute("DROP TYPE acesso_situacao")
    op.execute("DROP TYPE acesso_modo")
    op.execute("DROP TYPE produto_status")

    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
    op.execute("DROP EXTENSION IF EXISTS citext")
