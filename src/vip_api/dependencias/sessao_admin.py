"""Cookie e dependência de autenticação DO ADMINISTRADOR.

Gêmeo de sessao_cliente.py, escrito à parte e não parametrizado. A única coisa
que vem de lá é o NOME do cookie de cliente, usado para diferenciar 401 de
403 — é uma string, não uma decisão de autenticação.
"""

from dataclasses import dataclass

from fastapi import Depends, Request, Response
from sqlalchemy.orm import Session

from vip_api.banco import obter_sessao
from vip_api.configuracao import configuracao
from vip_api.dependencias.sessao_cliente import NOME_COOKIE as NOME_COOKIE_CLIENTE
from vip_api.erros.codigos import NAO_IDENTIFICADO, SEM_PERMISSAO
from vip_api.erros.excecoes import AppError
from vip_api.modelos.admin import AdminSessao, Administrador
from vip_api.servicos.admin import DURACAO_SESSAO, buscar_sessao_valida_admin

NOME_COOKIE = "vip_sessao_admin"


def gravar_cookie_admin(resposta: Response, token: str) -> None:
    resposta.set_cookie(
        key=NOME_COOKIE,
        value=token,
        max_age=int(DURACAO_SESSAO.total_seconds()),
        httponly=True,
        samesite="lax",
        path="/",
        # `secure` só em produção, igual ao cookie do cliente: fixo em True, o
        # desenvolvimento local em HTTP para de receber o cookie e some meia
        # hora até alguém descobrir que o navegador descartou em silêncio.
        secure=configuracao.AMBIENTE == "producao",
    )


def limpar_cookie_admin(resposta: Response) -> None:
    resposta.delete_cookie(key=NOME_COOKIE, path="/", samesite="lax", httponly=True)


@dataclass
class AdminAutenticado:
    administrador: Administrador
    sessao_admin: AdminSessao


def admin_autenticado(
    requisicao: Request, sessao: Session = Depends(obter_sessao)
) -> AdminAutenticado:
    """401 quando não há sessão de admin nenhuma; 403 quando quem bate está
    identificado como CLIENTE.

    A diferença importa para a tela: 401 manda para o login do painel, 403 diz
    "esta conta não é de administrador" — mandar um cliente para o login do
    painel faria ele tentar a senha que não tem.
    """
    token = requisicao.cookies.get(NOME_COOKIE, "")

    if not token:
        if requisicao.cookies.get(NOME_COOKIE_CLIENTE):
            raise AppError(
                codigo=SEM_PERMISSAO,
                mensagem="Esta área é restrita à equipe da loja.",
                status_code=403,
            )
        raise AppError(
            codigo=NAO_IDENTIFICADO,
            mensagem="Faça login para acessar o painel.",
            status_code=401,
        )

    encontrado = buscar_sessao_valida_admin(sessao, token)
    if encontrado is None:
        # Sessão expirada, revogada, conta desativada ou senha trocada depois
        # que ela abriu: tudo cai aqui, e tudo pede login de novo.
        raise AppError(
            codigo=NAO_IDENTIFICADO,
            mensagem="Sua sessão expirou. Faça login de novo.",
            status_code=401,
        )

    administrador, sessao_admin = encontrado
    # Nada de renovar_se_necessario aqui: a sessão do painel não desliza.
    return AdminAutenticado(administrador=administrador, sessao_admin=sessao_admin)
