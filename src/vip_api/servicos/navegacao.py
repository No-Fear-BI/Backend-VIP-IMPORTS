"""Rotas de navegação: marcas, coleções e categorias, todas com contagem.

A contagem conta SÓ produto visível (`status <> 'oculto'`), e sai de uma
agregação única por rota — nunca de um COUNT por marca dentro de um laço.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from vip_api.erros.codigos import COLECAO_NAO_ENCONTRADA
from vip_api.erros.excecoes import AppError
from vip_api.esquemas.navegacao import CategoriaItem, ColecaoItem, CorItem, MarcaItem
from vip_api.modelos.catalogo import Categoria, Cor, Marca, Produto, ProdutoVariacao
from vip_api.servicos.colecoes import COLECOES, colecao_por_slug, filtro_do_publico
from vip_api.servicos.produto_destinos import pertence_categoria

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


def listar_cores(sessao: Session) -> list[CorItem]:
    """A paleta do filtro da vitrine.

    `count(DISTINCT produtos.id)` e não `count(*)`: a mesma cor pode estar em
    duas variações do mesmo produto (grafias diferentes, dado anterior à
    revisão 0007, que ligou a cor sem reescrever o texto), e o produto contaria
    duas vezes. Cor sem produto visível continua na lista, com zero — quem
    acabou de cadastrar "Off-white" precisa vê-la na paleta.
    """
    linhas = sessao.execute(
        select(
            Cor.id,
            Cor.nome,
            Cor.slug,
            func.count(func.distinct(Produto.id)).label("total_produtos"),
        )
        .outerjoin(ProdutoVariacao, ProdutoVariacao.cor_id == Cor.id)
        .outerjoin(Produto, (Produto.id == ProdutoVariacao.produto_id) & _VISIVEL)
        .where(Cor.ativa.is_(True))
        .group_by(Cor.id)
        .order_by(Cor.ordem.asc(), Cor.nome.asc())
    ).all()

    return [
        CorItem(id=l.id, nome=l.nome, slug=l.slug, total_produtos=l.total_produtos)
        for l in linhas
    ]


def listar_colecoes(sessao: Session | None = None) -> list[ColecaoItem]:
    """Feminino e Masculino: constantes do código desde a 0015 (não há mais tabela)."""
    return [ColecaoItem(**colecao) for colecao in COLECOES]


def listar_categorias_da_colecao(sessao: Session, slug_colecao: str) -> list[CategoriaItem]:
    """`GET /colecoes/:slug/categorias`: as categorias ativas que têm ao menos uma peça
    visível do público `slug`. A categoria não pertence a coleção (0015), então uma
    categoria vazia naquele público não tem o que mostrar na página de categorias."""
    if colecao_por_slug(slug_colecao) is None:
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
        .join(
            Produto,
            pertence_categoria(Categoria.id) & _VISIVEL & filtro_do_publico(slug_colecao),
        )
        .where(Categoria.ativa.is_(True))
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
