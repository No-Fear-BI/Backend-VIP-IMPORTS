"""Categorias do produto (a principal + adicionais) e filtro por público, com EXISTS.

Desde a 0015 a categoria não tem coleção: um produto tem uma categoria principal, até
`MAXIMO_CATEGORIAS - 1` adicionais (tema, como "Coleção de verão", além do tipo de peça) e,
separadamente, o público (`feminino`/`masculino`).
"""
from sqlalchemy import delete, or_, select
from vip_api.erros.excecoes import AppError
from vip_api.modelos.catalogo import Categoria, Produto
from vip_api.modelos.produto_destinos import ProdutoCategoriaAdicional
from vip_api.servicos.colecoes import filtro_do_publico, flags_dos_publicos

MAXIMO_CATEGORIAS = 5


def pertence_categoria(categoria_id):
    adicional = select(ProdutoCategoriaAdicional.produto_id).where(
        ProdutoCategoriaAdicional.produto_id == Produto.id,
        ProdutoCategoriaAdicional.categoria_id == categoria_id,
    ).correlate(Produto, Categoria).exists()
    return or_(Produto.categoria_id == categoria_id, adicional)


def pertence_colecao(slug):
    """Produto do público `slug` (feminino ou masculino). Unissex entra nos dois."""
    return filtro_do_publico(slug)


def validar_destinos(sessao, ids, mantidos=()):
    """`mantidos`: categorias que o produto já tem. Inativa só é barrada quando
    está sendo ADICIONADA; quem já estava nela pode ser editado sem mexer nisso."""
    ids = list(ids or [])
    categorias = [sessao.get(Categoria, id) for id in ids]
    if not 1 <= len(categorias) <= MAXIMO_CATEGORIAS or any(
        not c or (not c.ativa and c.id not in mantidos) for c in categorias
    ):
        raise AppError('DADOS_INVALIDOS', 'Confira as categorias selecionadas.', 400,
                       campos={'categoriasIds': f'Escolha de 1 a {MAXIMO_CATEGORIAS} categorias ativas.'})
    if len({c.id for c in categorias}) != len(categorias):
        raise AppError('DADOS_INVALIDOS', 'Confira as categorias selecionadas.', 400,
                       campos={'categoriasIds': 'Não repita a mesma categoria.'})
    return categorias


def validar_publicos(slugs):
    """Pelo menos um público, e só feminino/masculino. Devolve (feminino, masculino)."""
    slugs = list(slugs or [])
    if not slugs or any(s not in ('feminino', 'masculino') for s in slugs):
        raise AppError('DADOS_INVALIDOS', 'Confira o público do produto.', 400,
                       campos={'publicos': 'Escolha Feminino, Masculino ou os dois.'})
    return flags_dos_publicos(slugs)


def definir_destinos(sessao, produto, categorias):
    produto.categoria_id = categorias[0].id
    sessao.execute(delete(ProdutoCategoriaAdicional).where(
        ProdutoCategoriaAdicional.produto_id == produto.id))
    for categoria in categorias[1:]:
        sessao.add(ProdutoCategoriaAdicional(produto_id=produto.id, categoria_id=categoria.id))
