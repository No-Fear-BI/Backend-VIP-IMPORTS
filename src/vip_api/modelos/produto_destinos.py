"""Categorias adicionais de um mesmo produto, sem duplicar seu cadastro."""
from sqlalchemy import ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column
from vip_api.modelos.base import Base


class ProdutoCategoriaAdicional(Base):
    __tablename__ = 'produto_categorias_adicionais'
    produto_id: Mapped[int] = mapped_column(Integer, ForeignKey('produtos.id', name='fk_destino_produto', ondelete='CASCADE'), primary_key=True)
    categoria_id: Mapped[int] = mapped_column(Integer, ForeignKey('categorias.id', name='fk_destino_categoria', ondelete='RESTRICT'), primary_key=True)
