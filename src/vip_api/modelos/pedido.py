"""Pedido: o que o cliente encomendou, com cópia dos dados dele no momento do envio."""

from datetime import datetime

from sqlalchemy import Boolean, ForeignKeyConstraint, Identity, Index, Integer, String, Text, false, func, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from vip_api.modelos.base import Base


class Pedido(Base):
    __tablename__ = "pedidos"
    __table_args__ = (
        ForeignKeyConstraint(
            ["cliente_id"], ["clientes.id"], name="fk_pedidos_cliente_id_clientes", ondelete="SET NULL"
        ),
        Index("ix_pedidos_recentes", text("criado_em DESC"), text("id DESC")),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    cliente_id: Mapped[int | None] = mapped_column(Integer)
    # Cópia: o pedido não muda se o cliente editar o cadastro depois.
    cliente_nome: Mapped[str | None] = mapped_column(String(120))
    cliente_email: Mapped[str] = mapped_column(Text)
    cliente_telefone: Mapped[str | None] = mapped_column(String(20))
    # Lista de {codigo, nome, marca, variacao}, a mesma que foi para o WhatsApp.
    itens: Mapped[list] = mapped_column(JSONB)
    pago: Mapped[bool] = mapped_column(Boolean, server_default=false())
    pago_em: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    criado_em: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
