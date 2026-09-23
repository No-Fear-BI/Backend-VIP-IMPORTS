from datetime import datetime
from sqlalchemy import Boolean, String, Text, CheckConstraint, ForeignKey, Integer, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from vip_api.modelos.base import Base

class DecisaoRevisao(Base):
    __tablename__ = 'review_decisions'
    __table_args__ = (CheckConstraint("status IN ('approved', 'rejected')", name='ck_review_decisions_status'), UniqueConstraint('produto_id', name='uq_revisao_produto'))
    product_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    produto_id: Mapped[int | None] = mapped_column(Integer, ForeignKey('produtos.id', name='fk_revisao_produto', ondelete='SET NULL'), nullable=True)
    publicado_no_catalogo: Mapped[bool] = mapped_column(Boolean, server_default=text('false'))
    status: Mapped[str] = mapped_column(String(12))
    translated_name: Mapped[str] = mapped_column(String(240))
    translated_details: Mapped[str] = mapped_column(Text)
    original_name: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(100))
    supplier: Mapped[str] = mapped_column(String(40))
    image: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())
