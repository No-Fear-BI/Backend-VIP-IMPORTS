"""Envio da seleção por WhatsApp e histórico do cliente."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from vip_api.banco import obter_sessao
from vip_api.dependencias.sessao_cliente import ClienteAutenticado, cliente_autenticado
from vip_api.esquemas.base import Pagina
from vip_api.esquemas.selecao import SelecaoResumo, SelecaoSaida
from vip_api.servicos.selecoes import (
    POR_PAGINA_MAXIMO,
    POR_PAGINA_PADRAO,
    criar_selecao,
    listar_selecoes,
)

roteador = APIRouter(tags=["selecoes"])


# Corpo vazio de propósito: a seleção é o carrinho atual da sessão. Mandar a
# lista de itens no corpo abriria espaço para o cliente enviar uma seleção
# diferente da que montou na tela.
@roteador.post("/selecoes", response_model=SelecaoSaida, status_code=201)
def enviar(
    atual: ClienteAutenticado = Depends(cliente_autenticado),
    sessao: Session = Depends(obter_sessao),
) -> SelecaoSaida:
    return criar_selecao(sessao, atual.cliente)


@roteador.get("/selecoes", response_model=Pagina[SelecaoResumo])
def historico(
    cursor: str | None = Query(None, description="Ausente na primeira página."),
    por_pagina: int = Query(
        POR_PAGINA_PADRAO,
        alias="porPagina",
        description=f"Máximo {POR_PAGINA_MAXIMO}; valores acima são limitados.",
    ),
    atual: ClienteAutenticado = Depends(cliente_autenticado),
    sessao: Session = Depends(obter_sessao),
) -> Pagina[SelecaoResumo]:
    return listar_selecoes(sessao, atual.cliente.id, cursor, por_pagina)
