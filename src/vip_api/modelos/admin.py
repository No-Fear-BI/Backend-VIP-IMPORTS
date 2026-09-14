"""Administradores e suas sessões.

Sistema de acesso separado do cliente: outra tabela, outro cookie, outro
prazo, nenhuma chave cruzando. Um `WHERE tipo` esquecido numa tabela única
viraria escalada de privilégio; aqui o token de cliente simplesmente não
existe onde o painel procura.
"""

from datetime import datetime

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKeyConstraint,
    Identity,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, INET, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vip_api.modelos.base import Base


class Administrador(Base):
    __tablename__ = "administradores"
    __table_args__ = (
        UniqueConstraint("email", name="uq_administradores_email"),
        # citext resolve a COMPARAÇÃO; esta CHECK (revisão 0006) resolve a
        # forma GRAVADA. Não é tautologia: `lower()` devolve text, e citext
        # comparado com text usa o operador de text, que diferencia caixa.
        CheckConstraint("email = lower(email)", name="ck_administradores_email_minusculo"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(CITEXT)
    senha_hash: Mapped[str] = mapped_column(Text)
    # Invalida sessões abertas sem apagar linha por linha: a checagem compara
    # admin_sessoes.criado_em com este campo.
    senha_alterada_em: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    ativo: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    ultimo_login_em: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    criado_em: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    sessoes: Mapped[list["AdminSessao"]] = relationship(back_populates="administrador")


class AdminSessao(Base):
    __tablename__ = "admin_sessoes"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_admin_sessoes_token_hash"),
        ForeignKeyConstraint(
            ["administrador_id"],
            ["administradores.id"],
            name="fk_admin_sessoes_administrador_id_administradores",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    administrador_id: Mapped[int] = mapped_column(Integer)
    token_hash: Mapped[str] = mapped_column(CHAR(64))
    criado_em: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    # 12 horas, sem renovação por uso — ao contrário da sessão de cliente.
    expira_em: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now() + interval '12 hours'")
    )
    revogado_em: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)

    administrador: Mapped["Administrador"] = relationship(back_populates="sessoes")
