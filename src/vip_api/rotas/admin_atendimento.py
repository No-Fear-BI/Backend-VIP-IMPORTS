"""Painel de conversas do atendimento Burnwood — o backend da tela.

O navegador chama `/api/v1/admin/atendimento/<caminho>`; estas rotas conferem
o caminho contra a lista de servicos/burnwood.py, acrescentam a key e o nome de
quem está logado, e repassam para `/v1/tenants/{slug}/<caminho>` na Burnwood.

Incluídas no roteador protegido de admin_painel.py: sem sessão de admin não
passa, e a varredura de testes/teste_protecao_admin.py cobre estas rotas sozinha.

Sucesso volta como a Burnwood mandou (JSON da Burnwood, em snake_case — não é
esquema nosso). Erro volta no envelope da API, `{erro: {codigo, mensagem}}`,
para o painel tratar como trata qualquer outro.
"""

import json
import logging

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from vip_api.dependencias.sessao_admin import AdminAutenticado, admin_autenticado
from vip_api.erros.codigos import ATENDIMENTO_INDISPONIVEL, ATENDIMENTO_ROTA_NAO_PERMITIDA
from vip_api.erros.excecoes import AppError
from vip_api.servicos import burnwood

logger = logging.getLogger("vip_api.burnwood")

roteador = APIRouter(prefix="/atendimento", tags=["admin"])

# Erros da Burnwood que a equipe pode encontrar no uso normal, já no texto
# que a tela mostra. O código vai em maiúsculas, como os nossos.
_MENSAGENS = {
    "conversation_assigned": "Outra pessoa já assumiu esta conversa.",
    "not_conversation_owner": "Só quem assumiu a conversa pode responder.",
    "invalid_transition": "Esta ação não vale mais para a conversa. Atualize a tela.",
    "automation_unavailable": "O agente de IA não está disponível agora.",
    "reply_window_closed": "O prazo para responder esta conversa já acabou.",
    "conversation_not_found": "Conversa não encontrada.",
    "permission_denied": "A key do atendimento não tem permissão para isso. Para conectar o WhatsApp, peça à Burnwood uma key manager.",
}


def _erro_da_burnwood(status: int, corpo: bytes) -> JSONResponse:
    try:
        codigo = json.loads(corpo)["error"]["code"]
    except (ValueError, KeyError, TypeError):
        codigo = "erro_atendimento"
    if status == 429:
        mensagem = "Muitas requisições ao atendimento. Aguarde alguns segundos."
    else:
        mensagem = _MENSAGENS.get(codigo, "O atendimento recusou a ação. Tente de novo.")
    return JSONResponse(
        status_code=status,
        content={"erro": {"codigo": str(codigo).upper(), "mensagem": mensagem}},
    )


async def _corpo_bruto(requisicao: Request) -> bytes | None:
    """O corpo do POST, sem validar: quem valida é a Burnwood. Dependência
    async só para ler o corpo — as rotas em si são síncronas como o resto da
    API, e a chamada à Burnwood roda no pool de threads, sem travar o servidor."""
    return await requisicao.body() if requisicao.method == "POST" else None


def _repassar(requisicao: Request, caminho: str, corpo: bytes | None, atual: AdminAutenticado) -> Response:
    # A rota já casa com o caminho; a lista de servicos/burnwood.py confere de
    # novo o formato do id e a ação, e é a fonte única do que é permitido.
    if not burnwood.chamada_permitida(requisicao.method, caminho):
        raise AppError(
            codigo=ATENDIMENTO_ROTA_NAO_PERMITIDA,
            mensagem="Esta ação do atendimento não está disponível no painel.",
            status_code=404,
        )
    try:
        resposta = burnwood.chamar(
            requisicao.method,
            caminho,
            list(requisicao.query_params.multi_items()),
            corpo,
            atual.administrador.nome,
        )
    except burnwood.BurnwoodIndisponivel:
        logger.exception("atendimento indisponível")
        raise AppError(
            codigo=ATENDIMENTO_INDISPONIVEL,
            mensagem="O atendimento está desligado ou fora do ar agora.",
            status_code=503,
        ) from None

    if resposta.status >= 400:
        return _erro_da_burnwood(resposta.status, resposta.corpo)
    if resposta.status == 204 or not resposta.corpo:
        # Nenhuma rota desta API devolve 204 (docs/para-o-frontend.md).
        return JSONResponse({"ok": True})
    return Response(content=resposta.corpo, status_code=resposta.status, media_type="application/json")


# Uma rota por chamada da lista, com o caminho da Burnwood: o que não está
# aqui nem chega nesta função (404 do roteador).


@roteador.get("/conversations")
def listar_conversas(requisicao: Request, atual: AdminAutenticado = Depends(admin_autenticado)) -> Response:
    return _repassar(requisicao, "conversations", None, atual)


@roteador.get("/conversations/{conversa_id}")
def obter_conversa(
    conversa_id: str, requisicao: Request, atual: AdminAutenticado = Depends(admin_autenticado)
) -> Response:
    return _repassar(requisicao, f"conversations/{conversa_id}", None, atual)


@roteador.get("/conversations/{conversa_id}/messages")
def listar_mensagens(
    conversa_id: str, requisicao: Request, atual: AdminAutenticado = Depends(admin_autenticado)
) -> Response:
    return _repassar(requisicao, f"conversations/{conversa_id}/messages", None, atual)


@roteador.post("/conversations/{conversa_id}/{acao}")
def agir_na_conversa(
    conversa_id: str,
    acao: str,
    requisicao: Request,
    corpo: bytes | None = Depends(_corpo_bruto),
    atual: AdminAutenticado = Depends(admin_autenticado),
) -> Response:
    """`acao`: takeover, reply, pause, resume, return-to-bot, resolve, close."""
    return _repassar(requisicao, f"conversations/{conversa_id}/{acao}", corpo, atual)


@roteador.get("/channels")
def listar_canais(requisicao: Request, atual: AdminAutenticado = Depends(admin_autenticado)) -> Response:
    return _repassar(requisicao, "channels", None, atual)


# ---------------------------------------------------------------- Configurações → WhatsApp
# O painel não tem papéis: todo administrador é dono da configuração da loja.


@roteador.get("/configuracao")
def configuracao_do_atendimento(atual: AdminAutenticado = Depends(admin_autenticado)) -> dict:
    """O que a key permite. `podeConectarWhatsapp` falso = key `operator`: a tela mostra só o status."""
    try:
        return {"podeConectarWhatsapp": burnwood.pode_configurar()}
    except burnwood.BurnwoodIndisponivel:
        logger.exception("atendimento indisponível")
        raise AppError(
            codigo=ATENDIMENTO_INDISPONIVEL,
            mensagem="O atendimento está desligado ou fora do ar agora.",
            status_code=503,
        ) from None


@roteador.get("/whatsapp")
def obter_whatsapp(requisicao: Request, atual: AdminAutenticado = Depends(admin_autenticado)) -> Response:
    """Estado da conexão: `{connected, provider, phone_number, display_name, state, updated_at}`."""
    return _repassar(requisicao, "whatsapp", None, atual)


@roteador.post("/whatsapp/connect")
def conectar_whatsapp(
    requisicao: Request,
    corpo: bytes | None = Depends(_corpo_bruto),
    atual: AdminAutenticado = Depends(admin_autenticado),
) -> Response:
    """Começa a conexão: `{connect_url, state, expires_in}`. A tela abre `connect_url` numa janela."""
    return _repassar(requisicao, "whatsapp/connect", corpo, atual)


@roteador.post("/whatsapp/connect/complete")
def concluir_whatsapp(
    requisicao: Request,
    corpo: bytes | None = Depends(_corpo_bruto),
    atual: AdminAutenticado = Depends(admin_autenticado),
) -> Response:
    """Fecha a conexão com o `state` (e o `phone_number_id`, se a janela mandou). 409 = o número
    ainda está sendo registrado; a tela tenta de novo. Quem confere o número é a Burnwood."""
    return _repassar(requisicao, "whatsapp/connect/complete", corpo, atual)

