"""Controle de entrada, lado da loja (seção 05): GET /acesso/estado e
POST /acesso/solicitar. Roteador FORA do portão (dependencias/acesso.py) — é
por aqui que o visitante barrado entende o motivo e pede liberação.

POST /acesso/senha (modo 2, senha compartilhada) continua sem construir.
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from vip_api.banco import obter_sessao
from vip_api.dependencias.sessao_cliente import (
    NOME_COOKIE,
    ClienteAutenticado,
    cliente_autenticado,
)
from vip_api.esquemas.acesso import EstadoAcesso, SolicitarAcessoEntrada
from vip_api.servicos.acesso import montar_estado, solicitar_acesso
from vip_api.servicos.cliente import atualizar_cliente, buscar_sessao_valida

roteador = APIRouter(prefix="/acesso", tags=["acesso"])


@roteador.get("/estado", response_model=EstadoAcesso)
def estado(requisicao: Request, sessao: Session = Depends(obter_sessao)) -> EstadoAcesso:
    """Nunca 401: sem sessão devolve `identificado: false` — é exatamente a
    informação que a tela precisa para decidir entre "identifique-se" e a
    loja."""
    encontrado = buscar_sessao_valida(sessao, requisicao.cookies.get(NOME_COOKIE, ""))
    return montar_estado(sessao, encontrado[0] if encontrado else None)


@roteador.post("/solicitar", response_model=EstadoAcesso)
def solicitar(
    corpo: SolicitarAcessoEntrada,
    atual: ClienteAutenticado = Depends(cliente_autenticado),
    sessao: Session = Depends(obter_sessao),
) -> EstadoAcesso:
    """200, não 201, e idempotente: pedir de novo devolve o mesmo estado. Como
    o identificar, a rota garante uma situação ("há um pedido meu na fila"),
    não cria um registro a cada chamada."""
    cliente = atualizar_cliente(sessao, atual.cliente, corpo.nome, corpo.telefone)
    return solicitar_acesso(sessao, cliente)
