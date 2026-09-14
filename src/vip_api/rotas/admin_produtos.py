"""Rotas de produto do painel (tarefa 55).

Este roteador NÃO tem proteção própria: ele é incluído dentro do roteador
protegido de rotas/admin_painel.py, e herda de lá o `Depends(exigir_admin)` do
grupo. Nenhuma rota daqui vai para a lista de exceções da varredura.
"""

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from vip_api.banco import obter_sessao
from vip_api.esquemas.admin_produto import (
    LoteEntrada,
    LoteSaida,
    ProdutoAdminDetalhe,
    ProdutoAdminItem,
    ProdutoCriar,
    ProdutoEditar,
    StatusProduto,
)
from vip_api.esquemas.base import Pagina
from vip_api.servicos.admin_produtos import (
    POR_PAGINA_MAXIMO,
    POR_PAGINA_PADRAO,
    FiltrosAdmin,
    alterar_em_lote,
    criar_produto,
    duplicar_produto,
    editar_produto,
    excluir_produto,
    listar_produtos,
    obter_produto,
)

roteador = APIRouter(prefix="/produtos", tags=["admin"])


@roteador.get("", response_model=Pagina[ProdutoAdminItem])
def listar(
    sessao: Session = Depends(obter_sessao),
    busca: str | None = Query(None, description="Nome ou código, parcial."),
    marca_id: int | None = Query(None, alias="marcaId"),
    categoria_id: int | None = Query(None, alias="categoriaId"),
    colecao_id: int | None = Query(None, alias="colecaoId"),
    status: StatusProduto | None = Query(
        None, description="Ausente traz TUDO, inclusive os ocultos."
    ),
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(
        POR_PAGINA_PADRAO, alias="porPagina", description=f"Máximo {POR_PAGINA_MAXIMO}."
    ),
) -> Pagina[ProdutoAdminItem]:
    return listar_produtos(
        sessao,
        FiltrosAdmin(
            busca=busca,
            marca_id=marca_id,
            categoria_id=categoria_id,
            colecao_id=colecao_id,
            status=status,
            pagina=pagina,
            por_pagina=por_pagina,
        ),
    )


@roteador.post("", response_model=ProdutoAdminDetalhe, status_code=201)
def criar(
    corpo: ProdutoCriar, sessao: Session = Depends(obter_sessao)
) -> ProdutoAdminDetalhe:
    return criar_produto(sessao, corpo)


# ANTES de /{produtoId}: "lote" casaria com o parâmetro de caminho e a
# requisição morreria num 422 de "isto não é um inteiro" em vez de chegar aqui.
@roteador.patch("/lote", response_model=LoteSaida)
def alterar_lote(corpo: LoteEntrada, sessao: Session = Depends(obter_sessao)) -> LoteSaida:
    alterados = alterar_em_lote(
        sessao,
        ids=corpo.ids,
        status=corpo.status,
        destaque=corpo.destaque,
        marca_id=corpo.marca_id,
        categoria_id=corpo.categoria_id,
    )
    return LoteSaida(alterados=alterados)


@roteador.get("/{produtoId}", response_model=ProdutoAdminDetalhe)
def detalhe(
    produto_id: int = Path(alias="produtoId"), sessao: Session = Depends(obter_sessao)
) -> ProdutoAdminDetalhe:
    return obter_produto(sessao, produto_id)


@roteador.patch("/{produtoId}", response_model=ProdutoAdminDetalhe)
def editar(
    corpo: ProdutoEditar,
    produto_id: int = Path(alias="produtoId"),
    sessao: Session = Depends(obter_sessao),
) -> ProdutoAdminDetalhe:
    return editar_produto(sessao, produto_id, corpo)


@roteador.delete("/{produtoId}")
def excluir(
    produto_id: int = Path(alias="produtoId"), sessao: Session = Depends(obter_sessao)
) -> dict[str, bool]:
    excluir_produto(sessao, produto_id)
    return {"ok": True}


@roteador.post("/{produtoId}/duplicar", response_model=ProdutoAdminDetalhe, status_code=201)
def duplicar(
    produto_id: int = Path(alias="produtoId"), sessao: Session = Depends(obter_sessao)
) -> ProdutoAdminDetalhe:
    return duplicar_produto(sessao, produto_id)
