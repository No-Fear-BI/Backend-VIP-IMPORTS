"""Cliente, sessão de cliente, favoritos e carrinho."""

from datetime import datetime

from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, INET, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vip_api.modelos.base import ACESSO_SITUACAO, Base


class Cliente(Base):
    __tablename__ = "clientes"
    __table_args__ = (
        UniqueConstraint("email", name="uq_clientes_email"),
        Index("ix_clientes_recentes", text("criado_em DESC"), text("id DESC")),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    # citext: "Jose@X.com" e "jose@x.com" são a mesma linha. Sem isso o mesmo
    # cliente vira dois cadastros e perde os favoritos.
    email: Mapped[str] = mapped_column(CITEXT)
    nome: Mapped[str | None] = mapped_column(String(120))
    telefone: Mapped[str | None] = mapped_column(String(20))
    acesso_status: Mapped[str] = mapped_column(ACESSO_SITUACAO, server_default="aprovado")
    ultimo_acesso_em: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    criado_em: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    sessoes: Mapped[list["ClienteSessao"]] = relationship(back_populates="cliente")


class ClienteSessao(Base):
    __tablename__ = "cliente_sessoes"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_cliente_sessoes_token_hash"),
        ForeignKeyConstraint(
            ["cliente_id"],
            ["clientes.id"],
            name="fk_cliente_sessoes_cliente_id_clientes",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    cliente_id: Mapped[int] = mapped_column(Integer)
    # SHA-256 hexadecimal do token. O token em si vai no cookie e nunca é
    # gravado: banco vazado não vira sessão de ninguém.
    token_hash: Mapped[str] = mapped_column(CHAR(64))
    criado_em: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    expira_em: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now() + interval '90 days'")
    )
    revogado_em: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)

    cliente: Mapped["Cliente"] = relationship(back_populates="sessoes")


class Favorito(Base):
    __tablename__ = "favoritos"
    __table_args__ = (
        ForeignKeyConstraint(
            ["cliente_id"],
            ["clientes.id"],
            name="fk_favoritos_cliente_id_clientes",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["produto_id"],
            ["produtos.id"],
            name="fk_favoritos_produto_id_produtos",
            ondelete="CASCADE",
        ),
        Index(
            "ix_favoritos_cliente_recentes",
            "cliente_id",
            text("criado_em DESC"),
            text("produto_id DESC"),
        ),
        Index("ix_favoritos_produto", "produto_id"),
    )

    cliente_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    produto_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    criado_em: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )


class Carrinho(Base):
    __tablename__ = "carrinhos"
    __table_args__ = (
        UniqueConstraint("visitante_token_hash", name="uq_carrinhos_visitante_token_hash"),
        ForeignKeyConstraint(
            ["cliente_id"],
            ["clientes.id"],
            name="fk_carrinhos_cliente_id_clientes",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "cliente_id IS NOT NULL OR visitante_token_hash IS NOT NULL",
            name="ck_carrinhos_cliente_ou_visitante",
        ),
        Index(
            "uq_carrinhos_cliente_ativo",
            "cliente_id",
            unique=True,
            postgresql_where=text("cliente_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    cliente_id: Mapped[int | None] = mapped_column(Integer)
    visitante_token_hash: Mapped[str | None] = mapped_column(CHAR(64))
    criado_em: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    itens: Mapped[list["CarrinhoItem"]] = relationship(
        back_populates="carrinho", cascade="all, delete-orphan"
    )


class CarrinhoItem(Base):
    __tablename__ = "carrinho_itens"
    __table_args__ = (
        ForeignKeyConstraint(
            ["carrinho_id"],
            ["carrinhos.id"],
            name="fk_carrinho_itens_carrinho_id_carrinhos",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["produto_id"],
            ["produtos.id"],
            name="fk_carrinho_itens_produto_id_produtos",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["variacao_id"],
            ["produto_variacoes.id"],
            name="fk_carrinho_itens_variacao_id_produto_variacoes",
            ondelete="SET NULL",
        ),
        CheckConstraint("quantidade > 0", name="ck_carrinho_itens_quantidade_positiva"),
        # NULLS NOT DISTINCT: sem isso, "produto sem variação" entraria no
        # carrinho quantas vezes o visitante clicasse.
        UniqueConstraint(
            "carrinho_id",
            "produto_id",
            "variacao_id",
            name="uq_carrinho_itens_carrinho_produto_variacao",
            postgresql_nulls_not_distinct=True,
        ),
        Index("ix_carrinho_itens_produto", "produto_id"),
        Index("ix_carrinho_itens_variacao", "variacao_id"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    carrinho_id: Mapped[int] = mapped_column(Integer)
    produto_id: Mapped[int] = mapped_column(Integer)
    variacao_id: Mapped[int | None] = mapped_column(Integer)
    quantidade: Mapped[int] = mapped_column(SmallInteger, server_default="1")
    observacao: Mapped[str | None] = mapped_column(String(280))
    criado_em: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    carrinho: Mapped["Carrinho"] = relationship(back_populates="itens")
