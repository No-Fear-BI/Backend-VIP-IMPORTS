"""Catálogo: coleções, marcas, categorias, produtos, imagens, variações e banners."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vip_api.modelos.base import PRODUTO_STATUS, VARIACAO_TIPO, Base
from vip_api.texto import normalizar


# As coleções Feminino e Masculino não são tabela: são o PÚBLICO do produto
# (`Produto.feminino` / `Produto.masculino`, as duas marcadas = unissex). As
# constantes e as expressões SQL ficam em `servicos/colecoes.py`.


class Marca(Base):
    __tablename__ = "marcas"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_marcas_slug"),
        Index(
            "ix_marcas_nome_trgm",
            "nome_busca",
            postgresql_using="gin",
            postgresql_ops={"nome_busca": "gin_trgm_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    nome: Mapped[str] = mapped_column(String(80))
    nome_busca: Mapped[str] = mapped_column(Text)
    slug: Mapped[str] = mapped_column(String(80))
    logo_url: Mapped[str | None] = mapped_column(Text)
    ordem: Mapped[int] = mapped_column(Integer, server_default="0")
    ativa: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    criado_em: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    produtos: Mapped[list["Produto"]] = relationship(back_populates="marca")


class Cor(Base):
    """O vocabulário de cores da loja (revisão 0007).

    Tabela de referência como Marca, e pelo mesmo motivo: o slug é a URL
    pública do filtro (`/todos?cor=preto`), então nasce do nome na criação e só
    muda quando alguém manda `slug` explicitamente.

    Não tem `nome_busca` — cor não entra na busca por texto do catálogo, que
    procura em nome de produto e de marca. Acrescentar a coluna por simetria
    seria manter um índice trigram que nenhuma consulta lê.
    """

    __tablename__ = "cores"
    __table_args__ = (UniqueConstraint("slug", name="uq_cores_slug"),)

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    nome: Mapped[str] = mapped_column(String(60))
    slug: Mapped[str] = mapped_column(String(60))
    ordem: Mapped[int] = mapped_column(Integer, server_default="0")
    ativa: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    criado_em: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    variacoes: Mapped[list["ProdutoVariacao"]] = relationship(back_populates="cor")


class Categoria(Base):
    __tablename__ = "categorias"
    __table_args__ = (
        # Categoria não pertence mais a coleção (0015): o slug é único na tabela.
        UniqueConstraint("slug", name="uq_categorias_slug"),
        CheckConstraint(
            "destaque = false OR destaque_ordem IS NOT NULL",
            name="ck_categorias_destaque_ordem",
        ),
        Index(
            "ix_categorias_destaque",
            "destaque_ordem",
            "id",
            postgresql_where=text("destaque"),
        ),
        # Card da home (0016): cada lado tem no máximo uma categoria.
        CheckConstraint("card_home IN ('esquerda', 'direita')", name="ck_categorias_card_home"),
        Index(
            "uq_categorias_card_home",
            "card_home",
            unique=True,
            postgresql_where=text("card_home IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    nome: Mapped[str] = mapped_column(String(80))
    slug: Mapped[str] = mapped_column(String(80))
    imagem_url: Mapped[str | None] = mapped_column(Text)
    destaque: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    destaque_ordem: Mapped[int | None] = mapped_column(Integer)
    ordem: Mapped[int] = mapped_column(Integer, server_default="0")
    ativa: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    # Card da home (0016): 'esquerda' (no lugar do Feminino) ou 'direita' (no do Masculino).
    card_home: Mapped[str | None] = mapped_column(String(10))
    card_home_imagem_url: Mapped[str | None] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )


class Produto(Base):
    __tablename__ = "produtos"
    __table_args__ = (
        UniqueConstraint("codigo", name="uq_produtos_codigo"),
        CheckConstraint("quantidade_disponivel >= 0", name="ck_produtos_quantidade_disponivel"),
        ForeignKeyConstraint(
            ["marca_id"], ["marcas.id"], name="fk_produtos_marca_id_marcas", ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ["categoria_id"],
            ["categorias.id"],
            name="fk_produtos_categoria_id_categorias",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "destaque = false OR destaque_ordem IS NOT NULL",
            name="ck_produtos_destaque_ordem",
        ),
        # Todo produto é de pelo menos um público (feminino, masculino ou os dois).
        CheckConstraint("feminino OR masculino", name="ck_produtos_publico"),
        # Os índices abaixo são a espinha dorsal da paginação por cursor:
        # coluna de filtro à esquerda, par de ordenação à direita. O DESC faz
        # parte da definição — sem ele o índice não serve à ordenação
        # `recentes`, e é por isso que aparece como text() e não como string.
        Index(
            "ix_produtos_pub_recentes",
            text("criado_em DESC"),
            text("id DESC"),
            postgresql_where=text("status <> 'oculto'::produto_status"),
        ),
        Index(
            "ix_produtos_pub_nome",
            "nome_ordenacao",
            "id",
            postgresql_where=text("status <> 'oculto'::produto_status"),
        ),
        Index(
            "ix_produtos_marca_recentes",
            "marca_id",
            text("criado_em DESC"),
            text("id DESC"),
            postgresql_where=text("status <> 'oculto'::produto_status"),
        ),
        Index(
            "ix_produtos_marca_nome",
            "marca_id",
            "nome_ordenacao",
            "id",
            postgresql_where=text("status <> 'oculto'::produto_status"),
        ),
        Index(
            "ix_produtos_categoria_recentes",
            "categoria_id",
            text("criado_em DESC"),
            text("id DESC"),
            postgresql_where=text("status <> 'oculto'::produto_status"),
        ),
        Index(
            "ix_produtos_categoria_nome",
            "categoria_id",
            "nome_ordenacao",
            "id",
            postgresql_where=text("status <> 'oculto'::produto_status"),
        ),
        # /feminino e /masculino: um par de índices parciais por público.
        Index(
            "ix_produtos_feminino_recentes",
            text("criado_em DESC"),
            text("id DESC"),
            postgresql_where=text("feminino AND status <> 'oculto'::produto_status"),
        ),
        Index(
            "ix_produtos_feminino_nome",
            "nome_ordenacao",
            "id",
            postgresql_where=text("feminino AND status <> 'oculto'::produto_status"),
        ),
        Index(
            "ix_produtos_masculino_recentes",
            text("criado_em DESC"),
            text("id DESC"),
            postgresql_where=text("masculino AND status <> 'oculto'::produto_status"),
        ),
        Index(
            "ix_produtos_masculino_nome",
            "nome_ordenacao",
            "id",
            postgresql_where=text("masculino AND status <> 'oculto'::produto_status"),
        ),
        # Sem WHERE: o painel lista os ocultos também.
        Index("ix_produtos_admin", "status", text("criado_em DESC"), text("id DESC")),
        Index(
            "ix_produtos_destaque",
            "destaque_ordem",
            "id",
            postgresql_where=text("destaque AND status <> 'oculto'::produto_status"),
        ),
        Index(
            "ix_produtos_relacionados",
            "categoria_id",
            "marca_id",
            "id",
            postgresql_where=text("status <> 'oculto'::produto_status"),
        ),
        Index(
            "ix_produtos_nome_trgm",
            "nome_ordenacao",
            postgresql_using="gin",
            postgresql_ops={"nome_ordenacao": "gin_trgm_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    codigo: Mapped[str] = mapped_column(String(32))
    codigo_origem: Mapped[str | None] = mapped_column(String(80))
    origem_url: Mapped[str | None] = mapped_column(Text)
    nome: Mapped[str] = mapped_column(String(180))
    # COLLATE "C" na coluna (revisão 0003): ordenar por byte passa a ser o
    # padrão, e a consulta não precisa mais repetir o COLLATE para casar
    # com o índice.
    nome_ordenacao: Mapped[str] = mapped_column(Text(collation="C"))
    descricao: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(PRODUTO_STATUS, server_default="normal")
    quantidade_disponivel: Mapped[int | None] = mapped_column(Integer)
    destaque: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    # Fora da página Novidades quando falso (0017); a janela de 14 dias vale além disso.
    em_novidades: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    destaque_ordem: Mapped[int | None] = mapped_column(Integer)
    marca_id: Mapped[int] = mapped_column(Integer)
    categoria_id: Mapped[int] = mapped_column(Integer)
    # Público do produto (0015). As duas marcadas = unissex.
    feminino: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    masculino: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    criado_em: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    marca: Mapped["Marca"] = relationship(back_populates="produtos")
    categoria: Mapped["Categoria"] = relationship(
        foreign_keys=[categoria_id],
        primaryjoin="Produto.categoria_id == Categoria.id",
        viewonly=True,
    )
    imagens: Mapped[list["ProdutoImagem"]] = relationship(
        back_populates="produto", cascade="all, delete-orphan"
    )
    variacoes: Mapped[list["ProdutoVariacao"]] = relationship(
        back_populates="produto", cascade="all, delete-orphan"
    )


# `nome_ordenacao` mora aqui, no listener do modelo, e não numa chamada do
# serviço: mais cedo ou mais tarde alguém cria produto por outro caminho
# (script de carga, painel, correção pontual) e esquece de normalizar. O
# listener não tem como ser esquecido — mas ele NÃO dispara em INSERT em
# massa via Core (`session.execute(insert(...))`), então carga em lote precisa
# usar objetos ORM ou preencher a coluna na mão.
@event.listens_for(Produto, "before_insert")
@event.listens_for(Produto, "before_update")
def _preencher_nome_ordenacao(mapper, conexao, alvo: Produto) -> None:
    alvo.nome_ordenacao = normalizar(alvo.nome or "")


@event.listens_for(Marca, "before_insert")
@event.listens_for(Marca, "before_update")
def _preencher_nome_busca(mapper, conexao, alvo: Marca) -> None:
    alvo.nome_busca = normalizar(alvo.nome or "")


class ProdutoImagem(Base):
    __tablename__ = "produto_imagens"
    __table_args__ = (
        ForeignKeyConstraint(
            ["produto_id"],
            ["produtos.id"],
            name="fk_produto_imagens_produto_id_produtos",
            ondelete="CASCADE",
        ),
        # DEFERRABLE: reordenar imagens passa por um instante com ordens
        # duplicadas dentro da mesma transação.
        UniqueConstraint(
            "produto_id",
            "ordem",
            name="uq_produto_imagens_produto_ordem",
            deferrable=True,
            initially="DEFERRED",
        ),
        Index(
            "uq_produto_imagens_capa",
            "produto_id",
            unique=True,
            postgresql_where=text("capa"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    produto_id: Mapped[int] = mapped_column(Integer)
    url: Mapped[str] = mapped_column(Text)
    alt: Mapped[str | None] = mapped_column(String(200))
    ordem: Mapped[int] = mapped_column(Integer, server_default="1")
    capa: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    criado_em: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    produto: Mapped["Produto"] = relationship(back_populates="imagens")


class ProdutoVariacao(Base):
    __tablename__ = "produto_variacoes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["produto_id"],
            ["produtos.id"],
            name="fk_produto_variacoes_produto_id_produtos",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "produto_id", "tipo", "valor", name="uq_produto_variacoes_produto_tipo_valor"
        ),
        # Alvo da FK composta de carrinho_itens (revisão 0005): `id` já é PK,
        # mas o PostgreSQL exige unicidade declarada no PAR referenciado.
        UniqueConstraint("id", "tipo", name="uq_produto_variacoes_id_tipo"),
        # Revisão 0007: variação de cor aponta para o vocabulário; variação de
        # tamanho, nunca. RESTRICT para excluir cor em uso virar 409 com a
        # contagem, e não apagar a variação que alguém tem no carrinho.
        ForeignKeyConstraint(
            ["cor_id"],
            ["cores.id"],
            name="fk_produto_variacoes_cor_id_cores",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "(tipo = 'cor'::variacao_tipo) = (cor_id IS NOT NULL)",
            name="ck_produto_variacoes_cor_id",
        ),
        Index("ix_produto_variacoes_cor", "cor_id", "produto_id"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    produto_id: Mapped[int] = mapped_column(Integer)
    tipo: Mapped[str] = mapped_column(VARIACAO_TIPO)
    # O texto EXIBIDO. Para tipo='cor' ele é o nome da cor no momento em que a
    # grade foi salva; quem filtra lê `cor_id`, nunca este campo (revisão 0007).
    valor: Mapped[str] = mapped_column(String(60))
    cor_id: Mapped[int | None] = mapped_column(Integer)
    disponivel: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    ordem: Mapped[int] = mapped_column(Integer, server_default="0")
    criado_em: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    produto: Mapped["Produto"] = relationship(back_populates="variacoes")
    cor: Mapped["Cor | None"] = relationship(back_populates="variacoes")


class Banner(Base):
    __tablename__ = "banners"
    __table_args__ = (
        Index("ix_banners_ativos", "ordem", "id", postgresql_where=text("ativo")),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    titulo: Mapped[str | None] = mapped_column(String(120))
    subtitulo: Mapped[str | None] = mapped_column(String(200))
    imagem_url: Mapped[str] = mapped_column(Text)
    imagem_url_mobile: Mapped[str | None] = mapped_column(Text)
    alt: Mapped[str | None] = mapped_column(String(200))
    link_url: Mapped[str | None] = mapped_column(Text)
    ordem: Mapped[int] = mapped_column(Integer, server_default="0")
    ativo: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    criado_em: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
