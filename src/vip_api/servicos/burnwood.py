"""Cliente da Burnwood (atendimento: chat da loja e painel de conversas).

A key (`BURNWOOD_API_KEY`) é lida aqui e só aqui, e nunca sai do servidor: o
navegador fala com a NOSSA API (rotas/admin_atendimento.py e
rotas/atendimento.py), que acrescenta a key e repassa.

A key é a única configuração: o slug da empresa e a chave pública do canal do
chat vêm de `GET /v1/integration`, guardados em memória por alguns minutos.
"""

import logging
import re
import time
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

import httpx

from vip_api.configuracao import configuracao

logger = logging.getLogger("vip_api.burnwood")

DESCOBERTA_VALIDADE_S = 5 * 60
TEMPO_LIMITE_S = 10.0

# As chamadas que o painel pode fazer, e nenhuma outra. O caminho é o que vem
# depois de /v1/tenants/{slug}/. Qualquer coisa fora desta lista é recusada:
# quem tem sessão de admin age com a key da empresa, então a key só serve para
# atendimento.
_ID = r"[0-9a-f-]{36}"
_PERMITIDAS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("GET", re.compile(r"^conversations$")),
    ("GET", re.compile(rf"^conversations/{_ID}$")),
    ("GET", re.compile(rf"^conversations/{_ID}/messages$")),
    (
        "POST",
        re.compile(
            rf"^conversations/{_ID}/(takeover|reply|pause|resume|return-to-bot|resolve|close)$"
        ),
    ),
    ("GET", re.compile(r"^channels$")),
    # Configurações → WhatsApp: ligar o número da loja à Burnwood. Conectar
    # exige key `manager` (permissão automations.configure); com `operator` a
    # Burnwood responde 403 e a tela só mostra o status.
    ("GET", re.compile(r"^whatsapp$")),
    ("POST", re.compile(r"^whatsapp/connect(/complete)?$")),
    # Desligar da Burnwood (o registro no provedor continua) e a verificação de
    # entrada (`operational` = uma mensagem real chegou). De propósito FORA da
    # lista: `whatsapp/provider-registration`, que apaga a conta do WhatsApp
    # Business no provedor e não tem volta — fica no portal da Burnwood.
    ("POST", re.compile(r"^whatsapp/disconnect$")),
    ("POST", re.compile(r"^whatsapp/readiness/(start|missed)$")),
    # Configurações → Mercado Pago: situação, pedidos aprovados (valor e
    # finalidade) e checkouts. Conectar a conta é no portal da Burnwood.
    ("GET", re.compile(r"^payments/mercadopago$")),
    ("GET", re.compile(r"^payments/mercadopago/(requests|checkouts)$")),
    ("POST", re.compile(r"^payments/mercadopago/(requests|checkouts)$")),
)

# Parâmetros de busca que a listagem e a linha do tempo aceitam; o resto cai.
PARAMETROS_PERMITIDOS = frozenset({"state", "channel_id", "q", "limit", "cursor", "after", "before"})


class BurnwoodIndisponivel(Exception):
    """Sem key, key recusada ou Burnwood fora do ar. A mensagem vai para o log,
    nunca para o navegador."""


@dataclass(frozen=True)
class RespostaBurnwood:
    status: int
    corpo: bytes


def chamada_permitida(metodo: str, caminho: str) -> bool:
    return any(m == metodo and padrao.match(caminho) for m, padrao in _PERMITIDAS)


def filtrar_parametros(parametros: list[tuple[str, str]]) -> list[tuple[str, str]]:
    return [(chave, valor) for chave, valor in parametros if chave in PARAMETROS_PERMITIDOS]


def nome_do_operador(nome: str) -> str:
    """`X-Burnwood-Operator`: até 100 caracteres imprimíveis. Quebra de linha
    num cabeçalho HTTP é recusada pela biblioteca, e a Burnwood recusa o resto."""
    limpo = "".join(c for c in nome if c.isprintable()).strip()
    return limpo[:100] or "Equipe VIP Imports"


def url_do_widget(url_api: str) -> str:
    """API e widget moram em hosts irmãos:
    api.dev.burnwood.com.br → dev.burnwood.com.br; api.burnwood.com.br → app.burnwood.com.br."""
    partes = urlsplit(url_api)
    host = partes.hostname or ""
    endereco = partes.netloc
    if host.startswith("api."):
        resto = host[4:]
        endereco = endereco.replace(host, "app.burnwood.com.br" if resto == "burnwood.com.br" else resto)
    return urlunsplit((partes.scheme, endereco, "", "", ""))


def _url_api() -> str:
    return configuracao.BURNWOOD_API_URL.rstrip("/")


def _cabecalhos(operador: str | None = None) -> dict[str, str]:
    if not configuracao.BURNWOOD_API_KEY:
        raise BurnwoodIndisponivel("BURNWOOD_API_KEY não configurada")
    cabecalhos = {
        "Authorization": f"Bearer {configuracao.BURNWOOD_API_KEY}",
        "Accept": "application/json",
    }
    if operador:
        cabecalhos["X-Burnwood-Operator"] = operador
    return cabecalhos


def _cliente_http() -> httpx.Client:
    """Ponto único de criação do cliente HTTP — os testes trocam o transporte aqui."""
    return httpx.Client(timeout=TEMPO_LIMITE_S)


_descoberta: dict | None = None
_descoberta_em = 0.0
_descoberta_key = ""


def descobrir() -> dict:
    """Quem é esta key: slug da empresa, papel, canais do chat. Em cache."""
    global _descoberta, _descoberta_em, _descoberta_key
    agora = time.monotonic()
    if (
        _descoberta is not None
        and _descoberta_key == configuracao.BURNWOOD_API_KEY
        and agora - _descoberta_em < DESCOBERTA_VALIDADE_S
    ):
        return _descoberta
    try:
        with _cliente_http() as http:
            resposta = http.get(f"{_url_api()}/v1/integration", headers=_cabecalhos())
    except httpx.HTTPError as falha:
        raise BurnwoodIndisponivel(f"falha ao falar com a Burnwood: {falha!r}") from falha
    if resposta.status_code != 200:
        raise BurnwoodIndisponivel(f"a Burnwood recusou a key ({resposta.status_code})")
    _descoberta = resposta.json()
    _descoberta_em = agora
    _descoberta_key = configuracao.BURNWOOD_API_KEY
    return _descoberta


PERMISSAO_CONFIGURAR = "automations.configure"


def pode_configurar() -> bool:
    """A key é `manager`? Sem isso a tela do WhatsApp só mostra o status."""
    return PERMISSAO_CONFIGURAR in (descobrir().get("permissions") or [])


def url_portal_pagamentos() -> str:
    """Página de Pagamentos da empresa no portal da Burnwood: é lá que se conecta
    a conta do Mercado Pago (o retorno do login do Mercado Pago volta para o portal)."""
    slug = descobrir()["tenant"]["slug"]
    portal = (configuracao.BURNWOOD_WIDGET_URL or url_do_widget(_url_api())).rstrip("/")
    return f"{portal}/t/{slug}/payments"


def esquecer_descoberta() -> None:
    global _descoberta
    _descoberta = None


def configuracao_do_widget() -> dict[str, str] | None:
    """O que a loja precisa para mostrar o chat, ou None quando ele está
    desligado (sem key, sem canal website, ou Burnwood fora do ar).

    Falha aqui nunca derruba a loja: o chat some e o motivo vai para o log."""
    if not configuracao.BURNWOOD_API_KEY:
        return None
    try:
        canais = descobrir().get("website_channels") or []
    except BurnwoodIndisponivel:
        logger.exception("chat desligado: Burnwood indisponível")
        return None
    canal = (
        next((c for c in canais if c.get("public_key") == configuracao.BURNWOOD_CHANNEL_KEY), None)
        or next((c for c in canais if c.get("agent_enabled")), None)
        or (canais[0] if canais else None)
    )
    if canal is None:
        logger.warning("chat desligado: a empresa não tem canal website na Burnwood")
        return None
    return {
        "widget_url": (configuracao.BURNWOOD_WIDGET_URL or url_do_widget(_url_api())).rstrip("/"),
        "chave_canal": canal["public_key"],
    }


def chamar(
    metodo: str,
    caminho: str,
    parametros: list[tuple[str, str]],
    corpo: bytes | None,
    operador: str,
) -> RespostaBurnwood:
    """Repassa `metodo caminho` para /v1/tenants/{slug}/<caminho>, agindo em
    nome de `operador` (fica na auditoria da Burnwood). Quem chama já conferiu
    `chamada_permitida`."""
    slug = descobrir()["tenant"]["slug"]
    cabecalhos = _cabecalhos(nome_do_operador(operador))
    if metodo == "POST":
        cabecalhos["Content-Type"] = "application/json"
    try:
        with _cliente_http() as http:
            resposta = http.request(
                metodo,
                f"{_url_api()}/v1/tenants/{slug}/{caminho}",
                params=filtrar_parametros(parametros),
                headers=cabecalhos,
                content=(corpo or b"{}") if metodo == "POST" else None,
            )
    except httpx.HTTPError as falha:
        raise BurnwoodIndisponivel(f"falha ao falar com a Burnwood: {falha!r}") from falha
    if resposta.status_code == 401:
        # Key revogada depois da descoberta: força descobrir de novo na próxima.
        esquecer_descoberta()
        raise BurnwoodIndisponivel("a Burnwood recusou a key (401)")
    return RespostaBurnwood(status=resposta.status_code, corpo=resposta.content)
