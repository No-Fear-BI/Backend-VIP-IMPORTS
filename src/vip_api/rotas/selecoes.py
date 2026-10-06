"""Envio da seleção por WhatsApp sem histórico."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from vip_api.banco import obter_sessao
from vip_api.dependencias.sessao_cliente import ClienteAutenticado, cliente_autenticado
from vip_api.esquemas.selecao import SelecaoSaida
from vip_api.servicos.selecoes import (
    criar_selecao,
)

roteador = APIRouter(tags=["selecoes"])


# Corpo vazio de propósito: a seleção é o carrinho atual da sessão. Mandar a
# lista de itens no corpo abriria espaço para o cliente enviar uma seleção
# diferente da que montou na tela.
@roteador.post("/selecoes", response_model=SelecaoSaida, status_code=200)
def enviar(
    atual: ClienteAutenticado = Depends(cliente_autenticado),
    sessao: Session = Depends(obter_sessao),
) -> SelecaoSaida:
    return criar_selecao(sessao, atual.cliente)
