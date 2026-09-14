"""Login e logout do painel — as DUAS rotas administrativas sem proteção.

É a única exceção ao roteador protegido (rotas/admin_painel.py), e é uma
exceção obrigatória: exigir sessão de admin para abrir a sessão de admin
tranca o painel para todo mundo, inclusive para quem tem a senha certa. O
logout fica junto porque precisa funcionar com a sessão já expirada — senão o
cookie morto fica no navegador sem jeito de sair.

Qualquer rota nova que precise ficar aqui fora tem que aparecer na lista de
exceções de testes/teste_protecao_admin.py, que é onde a decisão fica visível
na revisão do PR.
"""

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from vip_api.banco import obter_sessao
from vip_api.dependencias.sessao_admin import (
    NOME_COOKIE,
    gravar_cookie_admin,
    limpar_cookie_admin,
)
from vip_api.esquemas.admin import AdminEu, LoginEntrada
from vip_api.seguranca.limite import ESCOPO_LOGIN_ADMIN, LIMITE_LOGIN_ADMIN, registrar_tentativa
from vip_api.seguranca.rede import ip_do_visitante
from vip_api.servicos.admin import (
    autenticar_administrador,
    criar_sessao_admin,
    encerrar_sessao_admin,
)

roteador = APIRouter(tags=["admin"])


@roteador.post("/admin/sessao", response_model=AdminEu)
def entrar(
    corpo: LoginEntrada,
    requisicao: Request,
    resposta: Response,
    sessao: Session = Depends(obter_sessao),
) -> AdminEu:
    ip = ip_do_visitante(requisicao)
    # Escopo próprio: o balde do painel não é o mesmo da identificação do
    # cliente. Somados, um visitante teimoso na loja trancaria o login do
    # painel — e o admin ficaria de fora por causa de alguém que não controla.
    registrar_tentativa(sessao, ip, escopo=ESCOPO_LOGIN_ADMIN, limite=LIMITE_LOGIN_ADMIN)

    administrador = autenticar_administrador(sessao, corpo.email, corpo.senha)
    token = criar_sessao_admin(
        sessao, administrador, ip=ip, user_agent=requisicao.headers.get("user-agent")
    )
    gravar_cookie_admin(resposta, token)

    return AdminEu.model_validate(administrador)


@roteador.delete("/admin/sessao")
def sair(
    resposta: Response,
    requisicao: Request,
    sessao: Session = Depends(obter_sessao),
) -> dict[str, bool]:
    """Sem exigir sessão válida: sair tem que funcionar com o token já
    expirado, senão o cookie morto fica no navegador."""
    # Revoga no banco ANTES de limpar o cookie: apagar só o cookie deixaria o
    # token continuar valendo para quem o tivesse copiado.
    encerrar_sessao_admin(sessao, requisicao.cookies.get(NOME_COOKIE, ""))
    limpar_cookie_admin(resposta)
    return {"ok": True}
