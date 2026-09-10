"""Cookie e dependência de autenticação DO CLIENTE.

Este arquivo trata só do cliente. O administrador terá o seu, com outro nome
de cookie, outra tabela e outra dependência — escrito à parte, não
parametrizado. Uma função só, com um argumento `tipo`, é o desenho em que uma
troca de argumento faz um token de cliente abrir o painel.
"""

from dataclasses import dataclass

from fastapi import Depends, Request, Response
from sqlalchemy.orm import Session

from vip_api.banco import obter_sessao
from vip_api.configuracao import configuracao
from vip_api.erros.codigos import NAO_IDENTIFICADO
from vip_api.erros.excecoes import AppError
from vip_api.modelos.cliente import Cliente, ClienteSessao
from vip_api.servicos.cliente import (
    DURACAO_SESSAO,
    buscar_sessao_valida,
    renovar_se_necessario,
)

NOME_COOKIE = "vip_sessao_cliente"


def gravar_cookie_cliente(resposta: Response, token: str) -> None:
    resposta.set_cookie(
        key=NOME_COOKIE,
        value=token,
        max_age=int(DURACAO_SESSAO.total_seconds()),
        httponly=True,
        samesite="lax",
        path="/",
        # `secure` só em produção: com ele fixo, o desenvolvimento local em
        # HTTP para de receber o cookie e some meia hora até alguém descobrir
        # que o navegador está descartando em silêncio.
        secure=configuracao.AMBIENTE == "producao",
    )


def limpar_cookie_cliente(resposta: Response) -> None:
    resposta.delete_cookie(key=NOME_COOKIE, path="/", samesite="lax", httponly=True)


@dataclass
class ClienteAutenticado:
    cliente: Cliente
    sessao_cliente: ClienteSessao


def cliente_autenticado(
    requisicao: Request, sessao: Session = Depends(obter_sessao)
) -> ClienteAutenticado:
    token = requisicao.cookies.get(NOME_COOKIE, "")
    encontrado = buscar_sessao_valida(sessao, token)

    if encontrado is None:
        raise AppError(
            codigo=NAO_IDENTIFICADO,
            mensagem="É necessário se identificar para continuar.",
            status_code=401,
        )

    cliente, sessao_cliente = encontrado
    renovar_se_necessario(sessao, cliente, sessao_cliente)
    return ClienteAutenticado(cliente=cliente, sessao_cliente=sessao_cliente)
