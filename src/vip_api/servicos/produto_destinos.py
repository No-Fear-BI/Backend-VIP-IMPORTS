"""Filtros de destino com EXISTS: contagem e paginacao sem produtos repetidos."""
from sqlalchemy import or_, select
from vip_api.modelos.catalogo import Categoria, Produto
from vip_api.modelos.produto_destinos import ProdutoCategoriaAdicional


def pertence_categoria(categoria_id):
    adicional = select(ProdutoCategoriaAdicional.produto_id).where(
        ProdutoCategoriaAdicional.produto_id == Produto.id,
        ProdutoCategoriaAdicional.categoria_id == categoria_id,
    ).correlate(Produto, Categoria).exists()
    return or_(Produto.categoria_id == categoria_id, adicional)


def pertence_colecao(colecao_id):
    adicional = select(ProdutoCategoriaAdicional.produto_id).join(
        Categoria, Categoria.id == ProdutoCategoriaAdicional.categoria_id,
    ).where(
        ProdutoCategoriaAdicional.produto_id == Produto.id,
        Categoria.colecao_id == colecao_id,
    ).correlate(Produto).exists()
    return or_(Produto.colecao_id == colecao_id, adicional)
