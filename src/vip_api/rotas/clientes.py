"""Área do cliente: identificação sem senha, dados próprios e saída."""

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from vip_api.banco import obter_sessao
from vip_api.dependencias.sessao_cliente import (
    NOME_COOKIE,
    ClienteAutenticado,
    cliente_autenticado,
    gravar_cookie_cliente,
    limpar_cookie_cliente,
)
from vip_api.esquemas.cliente import ClienteAtualizarEntrada, ClienteEu, IdentificarEntrada
from vip_api.seguranca.limite import registrar_tentativa
from vip_api.seguranca.rede import ip_do_visitante
from vip_api.servicos.cliente import (
    atualizar_cliente,
    criar_sessao_cliente,
    encerrar_sessao_cliente,
    identificar_cliente,
)

roteador = APIRouter(tags=["clientes"])


@roteador.post("/clientes/identificar", response_model=ClienteEu)
def identificar(
    corpo: IdentificarEntrada,
    requisicao: Request,
    resposta: Response,
    sessao: Session = Depends(obter_sessao),
) -> ClienteEu:
    """Sempre 200, inclusive quando a conta é criada agora.

    A rota existe para ABRIR SESSÃO, não para criar registro — devolver 201 no
    primeiro acesso faria o frontend ramificar por status para chegar na mesma
    tela. Se a conta é nova ou antiga é detalhe do backend.
    """
    ip = ip_do_visitante(requisicao)
    registrar_tentativa(sessao, ip)

    # Duas camadas separadas de propósito: a verificação por e-mail da v2
    # entra exatamente aqui no meio, sem tocar em nenhuma das duas.
    cliente = identificar_cliente(sessao, corpo.email)
    token = criar_sessao_cliente(
        sessao, cliente, ip=ip, user_agent=requisicao.headers.get("user-agent")
    )
    gravar_cookie_cliente(resposta, token)

    return ClienteEu.model_validate(cliente)


@roteador.get("/clientes/eu", response_model=ClienteEu)
def eu(atual: ClienteAutenticado = Depends(cliente_autenticado)) -> ClienteEu:
    return ClienteEu.model_validate(atual.cliente)


@roteador.patch("/clientes/eu", response_model=ClienteEu)
def atualizar_eu(
    corpo: ClienteAtualizarEntrada,
    atual: ClienteAutenticado = Depends(cliente_autenticado),
    sessao: Session = Depends(obter_sessao),
) -> ClienteEu:
    # E-mail não está no corpo aceito: é a identidade da conta, trocar seria
    # virar outra pessoa.
    cliente = atualizar_cliente(sessao, atual.cliente, corpo.nome, corpo.telefone)
    return ClienteEu.model_validate(cliente)


@roteador.post("/clientes/sair")
def sair(
    resposta: Response,
    requisicao: Request,
    sessao: Session = Depends(obter_sessao),
) -> dict[str, bool]:
    """200 com corpo, não 204.

    A seção 1.4 do contrato lista 200 para exclusão e atualização bem-sucedidas,
    e o cliente HTTP do frontend desempacota JSON em toda resposta — 204 não tem
    corpo e quebraria esse caminho.
    """
    # Revoga no banco ANTES de limpar o cookie: apagar só o cookie deixaria o
    # token continuar valendo para quem tivesse copiado.
    encerrar_sessao_cliente(sessao, requisicao.cookies.get(NOME_COOKIE, ""))
    limpar_cookie_cliente(resposta)
    return {"ok": True}
