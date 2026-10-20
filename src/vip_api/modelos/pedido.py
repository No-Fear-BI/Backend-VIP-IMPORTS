"""Pedido (a seleção que o cliente enviou ao WhatsApp) e seus itens — dado CONGELADO.

Nada aqui é vivo: cada item guarda cópia em texto do que o cliente viu no
momento do envio, e o pedido guarda cópia dos dados do cliente. Se o produto for
renomeado ou excluído, ou o cadastro do cliente sumir, o painel continua
mostrando o que aconteceu de verdade.

Só o `status` muda depois da criação: é a equipe quem decide se o pedido foi
finalizado ou não.
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

from vip_api.modelos.base import PEDIDO_STATUS, Base


class Pedido(Base):
    __tablename__ = "pedidos"
    __table_args__ = (
        # Nulável e SEM cascata: cliente apagado não leva o pedido junto.
        ForeignKeyConstraint(
            ["cliente_id"],
            ["clientes.id"],
            name="fk_pedidos_cliente_id_clientes",
            ondelete="SET NULL",
        ),
        CheckConstraint("total_itens >= 0", name="ck_pedidos_total_itens"),
        # A listagem do painel: filtra por status e ordena do mais novo.
        Index("ix_pedidos_admin", "status", text("criado_em DESC"), text("id DESC")),
        # Apoia a FK e a busca do pedido em andamento do cliente (servicos/pedidos.py).
        Index("ix_pedidos_cliente", "cliente_id", text("criado_em DESC")),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    cliente_id: Mapped[int | None] = mapped_column(Integer)
    cliente_nome: Mapped[str | None] = mapped_column(String(120))
    cliente_email: Mapped[str] = mapped_column(CITEXT)
    cliente_telefone: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(PEDIDO_STATUS, server_default="em_andamento")
    # Quantas peças tem o pedido (uma linha por peça escolhida).
    total_itens: Mapped[int] = mapped_column(SmallInteger)
    criado_em: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    # Quando o status mudou pela última vez; igual a `criado_em` enquanto ninguém mexeu.
    atualizado_em: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    itens: Mapped[list["PedidoItem"]] = relationship(
        back_populates="pedido", cascade="all, delete-orphan"
    )


class PedidoItem(Base):
    __tablename__ = "pedido_itens"
    __table_args__ = (
        ForeignKeyConstraint(
            ["pedido_id"],
            ["pedidos.id"],
            name="fk_pedido_itens_pedido_id_pedidos",
            ondelete="CASCADE",
        ),
        # Nulável e SEM cascata: produto apagado deixa a linha intacta, só
        # perde o link. É o inverso do carrinho, que é dado vivo.
        ForeignKeyConstraint(
            ["produto_id"],
            ["produtos.id"],
            name="fk_pedido_itens_produto_id_produtos",
            ondelete="SET NULL",
        ),
        Index("ix_pedido_itens_pedido", "pedido_id", "ordem", "id"),
        Index("ix_pedido_itens_produto", "produto_id"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    pedido_id: Mapped[int] = mapped_column(Integer)
    produto_id: Mapped[int | None] = mapped_column(Integer)
    produto_codigo: Mapped[str] = mapped_column(String(32))
    produto_nome: Mapped[str] = mapped_column(String(180))
    marca_nome: Mapped[str] = mapped_column(String(80))
    categoria_nome: Mapped[str] = mapped_column(String(80))
    colecao_nome: Mapped[str] = mapped_column(String(40))
    imagem_url: Mapped[str | None] = mapped_column(Text)
    # Texto, não FK: se a variação for renomeada ou apagada, o pedido não muda
    # junto. Uma coluna por tipo, espelhando o carrinho (revisão 0005) — com uma
    # coluna só, o item enviado como "M / Preto" voltaria como "M".
    variacao_tamanho: Mapped[str | None] = mapped_column(String(60))
    variacao_cor: Mapped[str | None] = mapped_column(String(60))
    ordem: Mapped[int] = mapped_column(Integer, server_default="0")

    pedido: Mapped["Pedido"] = relationship(back_populates="itens")
