"""Monta a home inteira em QUATRO consultas ao banco.

O teto é dado: banners, destaques, categorias em destaque e marcas — uma
consulta cada. As capas dos destaques vêm no mesmo SELECT dos produtos, por
LEFT JOIN, e não numa consulta por produto (o N+1 clássico, que aqui viraria
13 consultas em vez de 4).
"""

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from vip_api.esquemas.home import BannerItem, CardColecao, Home
from vip_api.esquemas.navegacao import CategoriaDestaque
from vip_api.esquemas.produto import Capa, ProdutoItem, Referencia
from vip_api.modelos.catalogo import (
    Banner,
    Categoria,
    Marca,
    Produto,
    ProdutoImagem,
)
from vip_api.servicos.colecoes import nome_da_colecao, slug_da_colecao
from vip_api.servicos.navegacao import listar_marcas

LIMITE_DESTAQUES = 12


def _banners(sessao: Session) -> list[BannerItem]:
    linhas = sessao.execute(
        select(
            Banner.id,
            Banner.titulo,
            Banner.subtitulo,
            Banner.imagem_url,
            Banner.imagem_url_mobile,
            Banner.alt,
            Banner.link_url,
        )
        .where(Banner.ativo.is_(True))
        .order_by(Banner.ordem.asc(), Banner.id.asc())
    ).all()
    return [
        BannerItem(
            id=l.id,
            titulo=l.titulo,
            subtitulo=l.subtitulo,
            imagem_url=l.imagem_url,
            imagem_url_mobile=l.imagem_url_mobile,
            alt=l.alt,
            link_url=l.link_url,
        )
        for l in linhas
    ]


def _destaques(sessao: Session) -> list[ProdutoItem]:
    linhas = sessao.execute(
        select(
            Produto.id,
            Produto.codigo,
            Produto.nome,
            Produto.status,
            Produto.quantidade_disponivel,
            Produto.destaque,
            Marca.nome.label("marca_nome"),
            Marca.slug.label("marca_slug"),
            Categoria.nome.label("categoria_nome"),
            Categoria.slug.label("categoria_slug"),
            nome_da_colecao(Produto.feminino, Produto.masculino).label("colecao_nome"),
            slug_da_colecao(Produto.feminino).label("colecao_slug"),
            ProdutoImagem.url.label("capa_url"),
            ProdutoImagem.alt.label("capa_alt"),
        )
        .join(Marca, Marca.id == Produto.marca_id)
        .join(Categoria, Categoria.id == Produto.categoria_id)
        # A capa vem junto, no mesmo SELECT. É o que evita o N+1.
        .outerjoin(
            ProdutoImagem,
            and_(ProdutoImagem.produto_id == Produto.id, ProdutoImagem.capa.is_(True)),
        )
        .where(Produto.destaque.is_(True), Produto.status != "oculto")
        .order_by(Produto.destaque_ordem.asc(), Produto.id.asc())
        .limit(LIMITE_DESTAQUES)
    ).all()

    return [
        ProdutoItem(
            id=l.id,
            codigo=l.codigo,
            nome=l.nome,
            status=l.status,
            quantidade_disponivel=l.quantidade_disponivel,
            destaque=l.destaque,
            marca=Referencia(nome=l.marca_nome, slug=l.marca_slug),
            categoria=Referencia(nome=l.categoria_nome, slug=l.categoria_slug),
            colecao=Referencia(nome=l.colecao_nome, slug=l.colecao_slug),
            capa=Capa(url=l.capa_url, alt=l.capa_alt) if l.capa_url else None,
        )
        for l in linhas
    ]


def _categorias_da_home(
    sessao: Session,
) -> tuple[list[CategoriaDestaque], list[CardColecao]]:
    """As categorias em destaque E as dos cards de coleção, numa consulta só (o orçamento da
    home é de quatro). Categoria escondida não aparece em nenhum dos dois."""
    linhas = sessao.execute(
        select(
            Categoria.id,
            Categoria.nome,
            Categoria.slug,
            Categoria.imagem_url,
            Categoria.destaque,
            Categoria.card_home,
            Categoria.card_home_imagem_url,
        )
        .where(
            Categoria.ativa.is_(True),
            or_(Categoria.destaque.is_(True), Categoria.card_home.is_not(None)),
        )
        .order_by(Categoria.destaque_ordem.asc(), Categoria.id.asc())
    ).all()

    destaques = [
        CategoriaDestaque(id=l.id, nome=l.nome, slug=l.slug, imagem_url=l.imagem_url)
        for l in linhas
        if l.destaque
    ]
    cards = [
        CardColecao(
            lado=l.card_home,
            id=l.id,
            nome=l.nome,
            slug=l.slug,
            imagem_url=l.card_home_imagem_url or l.imagem_url,
        )
        for l in linhas
        if l.card_home
    ]
    return destaques, cards


def montar_home(sessao: Session) -> Home:
    categorias_destaque, cards_colecao = _categorias_da_home(sessao)
    return Home(
        banners=_banners(sessao),
        destaques=_destaques(sessao),
        categorias_destaque=categorias_destaque,
        cards_colecao=cards_colecao,
        marcas=listar_marcas(sessao),
    )
