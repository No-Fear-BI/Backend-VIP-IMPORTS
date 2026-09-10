"""Seleção enviada e seus itens — dado CONGELADO.

Nada aqui é vivo: cada item guarda cópia em texto do que o cliente viu no
momento do envio. Se o produto for renomeado ou excluído depois, o painel de
atendimento continua mostrando o que o cliente realmente viu.
"""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vip_api.modelos.base import Base


class Selecao(Base):
    __tablename__ = "selecoes"
    __table_args__ = (
        # Nulável e SEM cascata: cliente apagado não leva o histórico junto.
        ForeignKeyConstraint(
            ["cliente_id"],
            ["clientes.id"],
            name="fk_selecoes_cliente_id_clientes",
            ondelete="SET NULL",
        ),
        CheckConstraint("total_itens >= 0", name="ck_selecoes_total_itens"),
        Index("ix_selecoes_recentes", text("criado_em DESC"), text("id DESC")),
        Index("ix_selecoes_cliente", "cliente_id", text("criado_em DESC")),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    cliente_id: Mapped[int | None] = mapped_column(Integer)
    cliente_nome: Mapped[str | None] = mapped_column(String(120))
    cliente_email: Mapped[str] = mapped_column(CITEXT)
    cliente_telefone: Mapped[str | None] = mapped_column(String(20))
    observacao: Mapped[str | None] = mapped_column(Text)
    total_itens: Mapped[int] = mapped_column(SmallInteger)
    criado_em: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    itens: Mapped[list["SelecaoItem"]] = relationship(
        back_populates="selecao", cascade="all, delete-orphan"
    )


class SelecaoItem(Base):
    __tablename__ = "selecao_itens"
    __table_args__ = (
        ForeignKeyConstraint(
            ["selecao_id"],
            ["selecoes.id"],
            name="fk_selecao_itens_selecao_id_selecoes",
            ondelete="CASCADE",
        ),
        # Nulável e SEM cascata: produto apagado deixa a linha intacta, só
        # perde o link. É o inverso do carrinho, que é dado vivo.
        ForeignKeyConstraint(
            ["produto_id"],
            ["produtos.id"],
            name="fk_selecao_itens_produto_id_produtos",
            ondelete="SET NULL",
        ),
        CheckConstraint("quantidade > 0", name="ck_selecao_itens_quantidade_positiva"),
        Index("ix_selecao_itens_selecao", "selecao_id", "ordem", "id"),
        Index("ix_selecao_itens_produto", "produto_id"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    selecao_id: Mapped[int] = mapped_column(Integer)
    produto_id: Mapped[int | None] = mapped_column(Integer)
    produto_codigo: Mapped[str] = mapped_column(String(32))
    produto_nome: Mapped[str] = mapped_column(String(180))
    marca_nome: Mapped[str] = mapped_column(String(80))
    categoria_nome: Mapped[str] = mapped_column(String(80))
    colecao_nome: Mapped[str] = mapped_column(String(40))
    imagem_url: Mapped[str | None] = mapped_column(Text)
    # Texto, não enum: se o enum de variação mudar, o histórico não muda junto.
    variacao_tipo: Mapped[str | None] = mapped_column(String(20))
    variacao_valor: Mapped[str | None] = mapped_column(String(60))
    quantidade: Mapped[int] = mapped_column(SmallInteger, server_default="1")
    observacao: Mapped[str | None] = mapped_column(String(280))
    ordem: Mapped[int] = mapped_column(Integer, server_default="0")
    criado_em: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    selecao: Mapped["Selecao"] = relationship(back_populates="itens")
