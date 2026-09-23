"""Rotas de navegação do catálogo: marcas, coleções e categorias."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from vip_api.banco import obter_sessao
from vip_api.esquemas.navegacao import CategoriaItem, ColecaoItem, CorItem, MarcaItem
from vip_api.servicos.navegacao import (
    listar_categorias_da_colecao,
    listar_colecoes,
    listar_cores,
    listar_marcas,
)

roteador = APIRouter(tags=["navegacao"])


@roteador.get("/marcas", response_model=list[MarcaItem])
def marcas(sessao: Session = Depends(obter_sessao)) -> list[MarcaItem]:
    return listar_marcas(sessao)


@roteador.get("/cores", response_model=list[CorItem])
def cores(sessao: Session = Depends(obter_sessao)) -> list[CorItem]:
    """A paleta do filtro `?cor=` da listagem. Só as cores ativas."""
    return listar_cores(sessao)


@roteador.get("/colecoes", response_model=list[ColecaoItem])
def colecoes(sessao: Session = Depends(obter_sessao)) -> list[ColecaoItem]:
    return listar_colecoes(sessao)


# Não existe GET /categorias/:slug: o slug de categoria é único por coleção,
# então "bolsas" sozinho não identifica nada.
@roteador.get("/colecoes/{slug}/categorias", response_model=list[CategoriaItem])
def categorias_da_colecao(
    slug: str, sessao: Session = Depends(obter_sessao)
) -> list[CategoriaItem]:
    return listar_categorias_da_colecao(sessao, slug)
