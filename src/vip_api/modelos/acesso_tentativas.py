"""Contagem de tentativas de acesso por IP — espelho da migração 0004."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Identity,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import INET, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from vip_api.modelos.base import Base


class TentativaAcesso(Base):
    __tablename__ = "tentativas_acesso"
    __table_args__ = (
        UniqueConstraint(
            "escopo", "ip", "janela", name="uq_tentativas_acesso_escopo_ip_janela"
        ),
        CheckConstraint("tentativas > 0", name="ck_tentativas_acesso_positivas"),
        Index("ix_tentativas_acesso_janela", "janela"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    escopo: Mapped[str] = mapped_column(String(30))
    ip: Mapped[str] = mapped_column(INET)
    janela: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    tentativas: Mapped[int] = mapped_column(Integer, server_default="1")
