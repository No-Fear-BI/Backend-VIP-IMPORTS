"""Filtros de destino com EXISTS: contagem e paginacao sem produtos repetidos."""
from sqlalchemy import delete, or_, select
from vip_api.erros.excecoes import AppError
from vip_api.modelos.catalogo import Colecao
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


def validar_destinos(sessao, ids):
    categorias = [sessao.get(Categoria, id) for id in ids] if ids else []
    if not 1 <= len(categorias) <= 2 or any(
        not c or not c.ativa or not sessao.get(Colecao, c.colecao_id).ativa
        for c in categorias
    ):
        raise AppError('DADOS_INVALIDOS', 'Confira as categorias selecionadas.', 400,
                       campos={'categoriasIds': 'Escolha uma categoria ativa para cada coleção marcada.'})
    if len({c.colecao_id for c in categorias}) != len(categorias):
        raise AppError('DADOS_INVALIDOS', 'Confira as categorias selecionadas.', 400,
                       campos={'categoriasIds': 'Escolha no máximo uma categoria por coleção.'})
    return categorias


def definir_destinos(sessao, produto, categorias):
    produto.categoria_id = categorias[0].id
    produto.colecao_id = categorias[0].colecao_id
    sessao.execute(delete(ProdutoCategoriaAdicional).where(
        ProdutoCategoriaAdicional.produto_id == produto.id))
    for categoria in categorias[1:]:
        sessao.add(ProdutoCategoriaAdicional(produto_id=produto.id, categoria_id=categoria.id))
