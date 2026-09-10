"""GET /api/v1/produtos — listagem pública do catálogo."""

from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from vip_api.banco import obter_sessao
from vip_api.esquemas.base import Pagina
from vip_api.esquemas.produto import ProdutoDetalhe, ProdutoItem
from vip_api.servicos.catalogo import (
    POR_PAGINA_MAXIMO,
    POR_PAGINA_PADRAO,
    FiltrosProduto,
    listar_produtos,
    listar_relacionados,
    obter_produto,
)

roteador = APIRouter(tags=["produtos"])


@roteador.get("/produtos", response_model=Pagina[ProdutoItem])
def listar(
    sessao: Session = Depends(obter_sessao),
    colecao: str | None = Query(None, description="Slug da coleção: feminino ou masculino."),
    categoria: str | None = Query(
        None, description="Slug da categoria. Exige `colecao` junto — o slug é único por coleção."
    ),
    marca: str | None = Query(
        None, description="Slug da marca. Aceita várias separadas por vírgula."
    ),
    busca: str | None = Query(None, description="Filtra por nome do produto ou da marca."),
    ordem: Literal["recentes", "nome"] = Query("recentes"),
    cursor: str | None = Query(None, description="Ausente na primeira página."),
    por_pagina: int = Query(
        POR_PAGINA_PADRAO,
        alias="porPagina",
        description=f"Máximo {POR_PAGINA_MAXIMO}; valores acima são limitados, não recusados.",
    ),
) -> Pagina[ProdutoItem]:
    return listar_produtos(
        sessao,
        FiltrosProduto(
            colecao=colecao,
            categoria=categoria,
            marca=marca,
            busca=busca,
            ordem=ordem,
            cursor=cursor,
            por_pagina=por_pagina,
        ),
    )


@roteador.get("/produtos/{codigo}", response_model=ProdutoDetalhe)
def detalhe(codigo: str, sessao: Session = Depends(obter_sessao)) -> ProdutoDetalhe:
    return obter_produto(sessao, codigo)


@roteador.get("/produtos/{codigo}/relacionados", response_model=list[ProdutoItem])
def relacionados(codigo: str, sessao: Session = Depends(obter_sessao)) -> list[ProdutoItem]:
    return listar_relacionados(sessao, codigo)
