"""Rotas de navegação: marcas, coleções e categorias, todas com contagem.

A contagem conta SÓ produto visível (`status <> 'oculto'`), e sai de uma
agregação única por rota — nunca de um COUNT por marca dentro de um laço.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from vip_api.erros.codigos import COLECAO_NAO_ENCONTRADA
from vip_api.erros.excecoes import AppError
from vip_api.esquemas.navegacao import CategoriaItem, ColecaoItem, MarcaItem
from vip_api.modelos.catalogo import Categoria, Colecao, Marca, Produto

# `status <> 'oculto'` vive DENTRO do ON do LEFT JOIN, não no WHERE. No WHERE
# ele descartaria a linha inteira da marca sem produto visível, e "Goyard (0)"
# sumiria da lista em vez de aparecer com zero.
_VISIVEL = Produto.status != "oculto"


def listar_marcas(sessao: Session) -> list[MarcaItem]:
    linhas = sessao.execute(
        select(
            Marca.id,
            Marca.nome,
            Marca.slug,
            Marca.logo_url,
            func.count(Produto.id).label("total_produtos"),
        )
        .outerjoin(Produto, (Produto.marca_id == Marca.id) & _VISIVEL)
        .where(Marca.ativa.is_(True))
        .group_by(Marca.id)
        .order_by(Marca.ordem.asc(), Marca.nome.asc())
    ).all()

    return [
        MarcaItem(
            id=linha.id,
            nome=linha.nome,
            slug=linha.slug,
            logo_url=linha.logo_url,
            total_produtos=linha.total_produtos,
        )
        for linha in linhas
    ]


def listar_colecoes(sessao: Session) -> list[ColecaoItem]:
    linhas = sessao.execute(
        select(Colecao.id, Colecao.nome, Colecao.slug)
        .where(Colecao.ativa.is_(True))
        .order_by(Colecao.ordem.asc(), Colecao.id.asc())
    ).all()
    return [ColecaoItem(id=l.id, nome=l.nome, slug=l.slug) for l in linhas]


def listar_categorias_da_colecao(sessao: Session, slug_colecao: str) -> list[CategoriaItem]:
    """`GET /colecoes/:slug/categorias`. Não existe `/categorias/:slug` sozinho:
    o slug é único por coleção, e "bolsas" sem a coleção não identifica nada."""
    colecao_id = sessao.scalar(select(Colecao.id).where(Colecao.slug == slug_colecao))
    if colecao_id is None:
        raise AppError(
            codigo=COLECAO_NAO_ENCONTRADA,
            mensagem="Coleção não encontrada.",
            status_code=404,
        )

    linhas = sessao.execute(
        select(
            Categoria.id,
            Categoria.nome,
            Categoria.slug,
            Categoria.imagem_url,
            func.count(Produto.id).label("total_produtos"),
        )
        .outerjoin(Produto, (Produto.categoria_id == Categoria.id) & _VISIVEL)
        .where(Categoria.colecao_id == colecao_id, Categoria.ativa.is_(True))
        .group_by(Categoria.id)
        .order_by(Categoria.ordem.asc(), Categoria.nome.asc())
    ).all()

    return [
        CategoriaItem(
            id=linha.id,
            nome=linha.nome,
            slug=linha.slug,
            imagem_url=linha.imagem_url,
            total_produtos=linha.total_produtos,
        )
        for linha in linhas
    ]
