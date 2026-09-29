"""Controle de acesso da seção 05 do contrato — modelado e CONGELADO.

Não há rota usando estas tabelas hoje, e isso é deliberado: remodelar o banco
depois de 11 mil produtos e clientes reais cadastrados é o cenário que o plano
existe para evitar. Não apague por parecer código morto.
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
from sqlalchemy.orm import Mapped, mapped_column

from vip_api.modelos.base import ACESSO_MODO, ACESSO_SITUACAO, Base


class AcessoConfig(Base):
    __tablename__ = "acesso_config"
    __table_args__ = (
        ForeignKeyConstraint(
            ["atualizado_por_admin_id"],
            ["administradores.id"],
            name="fk_acesso_config_atualizado_por_admin_id_administradores",
            ondelete="SET NULL",
        ),
        # Linha única: o CHECK torna fisicamente impossível uma segunda config.
        CheckConstraint("id = 1", name="ck_acesso_config_linha_unica"),
        CheckConstraint(
            "modo <> 'senha_compartilhada' OR senha_hash IS NOT NULL",
            name="ck_acesso_config_senha_obrigatoria",
        ),
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, server_default="1")
    modo: Mapped[str] = mapped_column(ACESSO_MODO, server_default="aprovacao")
    senha_hash: Mapped[str | None] = mapped_column(Text)
    mensagem_bloqueio: Mapped[str | None] = mapped_column(Text)
    atualizado_por_admin_id: Mapped[int | None] = mapped_column(Integer)
    atualizado_em: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )


class AcessoSolicitacao(Base):
    __tablename__ = "acesso_solicitacoes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["cliente_id"],
            ["clientes.id"],
            name="fk_acesso_solicitacoes_cliente_id_clientes",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["decidido_por_admin_id"],
            ["administradores.id"],
            name="fk_acesso_solicitacoes_decidido_por_admin_id_administradores",
            ondelete="SET NULL",
        ),
        # Ou está pendente e sem data de decisão, ou decidida e com data.
        CheckConstraint(
            "(situacao = 'pendente') = (decidido_em IS NULL)",
            name="ck_acesso_solicitacoes_decisao",
        ),
        Index(
            "uq_acesso_solicitacoes_pendente",
            "cliente_id",
            unique=True,
            postgresql_where=text("situacao = 'pendente'::acesso_situacao"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    cliente_id: Mapped[int] = mapped_column(Integer)
    email: Mapped[str] = mapped_column(CITEXT)
    nome: Mapped[str | None] = mapped_column(String(120))
    telefone: Mapped[str | None] = mapped_column(String(20))
    situacao: Mapped[str] = mapped_column(ACESSO_SITUACAO, server_default="pendente")
    motivo: Mapped[str | None] = mapped_column(Text)
    decidido_por_admin_id: Mapped[int | None] = mapped_column(Integer)
    decidido_em: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    criado_em: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
