"""Atendimento Burnwood: rota do painel (repasse com a key) e rota do widget.

A Burnwood é simulada por um transporte falso do httpx: nenhum teste sai para
a rede, e cada um enxerga exatamente o que foi enviado (URL, cabeçalhos,
corpo) para conferir que a key só vai para a Burnwood e só nas rotas da lista.
"""

import json

import httpx
import pytest

from vip_api.configuracao import configuracao
from vip_api.modelos.acesso import AcessoConfig
from vip_api.servicos import burnwood

KEY = "bwk_teste_nao_e_de_verdade"
API = "https://api.dev.burnwood.com.br"
CONVERSA = "0b6f1c1e-6a3f-4c4e-9d2a-1f2e3d4c5b6a"
ROTA = "/api/v1/admin/atendimento"

INTEGRACAO = {
    "tenant": {"slug": "vip-import", "name": "VIP Import"},
    "api_key": {"name": "Site", "role": "operator"},
    "permissions": ["conversations.read"],
    "website_channels": [
        {"name": "Antigo", "public_key": "wk_sem_agente", "allowed_origins": [], "agent_enabled": False},
        {"name": "Site", "public_key": "wk_com_agente", "allowed_origins": [], "agent_enabled": True},
    ],
}


class BurnwoodFalsa:
    """Responde /v1/integration e o que o teste mandar; guarda cada chamada."""

    def __init__(self) -> None:
        self.chamadas: list[httpx.Request] = []
        self.respostas: dict[tuple[str, str], httpx.Response] = {}
        self.fora_do_ar = False

    def responder(self, metodo: str, caminho: str, status: int = 200, corpo=None) -> None:
        self.respostas[(metodo, caminho)] = httpx.Response(status, json=corpo)

    def __call__(self, requisicao: httpx.Request) -> httpx.Response:
        self.chamadas.append(requisicao)
        if self.fora_do_ar:
            raise httpx.ConnectError("fora do ar", request=requisicao)
        if requisicao.url.path == "/v1/integration":
            return httpx.Response(200, json=INTEGRACAO)
        resposta = self.respostas.get((requisicao.method, requisicao.url.path))
        return resposta if resposta is not None else httpx.Response(404, json={"error": {"code": "not_found"}})


@pytest.fixture
def falsa(monkeypatch) -> BurnwoodFalsa:
    falsa = BurnwoodFalsa()
    monkeypatch.setattr(configuracao, "BURNWOOD_API_KEY", KEY)
    monkeypatch.setattr(configuracao, "BURNWOOD_API_URL", API)
    monkeypatch.setattr(configuracao, "BURNWOOD_CHANNEL_KEY", "")
    monkeypatch.setattr(configuracao, "BURNWOOD_WIDGET_URL", "")
    monkeypatch.setattr(
        burnwood, "_cliente_http", lambda: httpx.Client(transport=httpx.MockTransport(falsa))
    )
    burnwood.esquecer_descoberta()
    yield falsa
    burnwood.esquecer_descoberta()


def _repasses(falsa: BurnwoodFalsa) -> list[httpx.Request]:
    return [c for c in falsa.chamadas if c.url.path != "/v1/integration"]


# ---------------------------------------------------------------- quem passa


def teste_sem_sessao_nao_passa(sem_sessao, falsa):
    resposta = sem_sessao.get(f"{ROTA}/conversations")
    assert resposta.status_code == 401
    assert falsa.chamadas == []


def teste_sessao_de_cliente_nao_passa(cliente_logado, falsa):
    resposta = cliente_logado.get(f"{ROTA}/conversations")
    assert resposta.status_code == 403
    assert falsa.chamadas == []


@pytest.mark.parametrize(
    "metodo, caminho",
    [
        ("GET", "users"),
        ("GET", "api-keys"),
        ("POST", "conversations"),
        ("GET", f"conversations/{CONVERSA}/notes"),
    ],
)
def teste_rota_que_nao_existe_nao_chega_na_burnwood(admin_logado, falsa, metodo, caminho):
    resposta = admin_logado.request(metodo, f"{ROTA}/{caminho}", json={} if metodo == "POST" else None)
    assert resposta.status_code in (404, 405)
    assert _repasses(falsa) == []


@pytest.mark.parametrize(
    "metodo, caminho",
    [
        ("POST", f"conversations/{CONVERSA}/delete"),
        ("POST", f"conversations/{CONVERSA}/assign"),
        ("GET", "conversations/nao-e-um-id"),
        ("POST", "conversations/nao-e-um-id/takeover"),
    ],
)
def teste_acao_ou_id_fora_da_lista_nao_chega_na_burnwood(admin_logado, falsa, metodo, caminho):
    resposta = admin_logado.request(metodo, f"{ROTA}/{caminho}", json={} if metodo == "POST" else None)
    assert resposta.status_code == 404
    assert resposta.json()["erro"]["codigo"] == "ATENDIMENTO_ROTA_NAO_PERMITIDA"
    assert _repasses(falsa) == []


@pytest.mark.parametrize("caminho", ["conversations/../../integration", "conversations/%2e%2e/%2e%2e/integration"])
def teste_subir_de_pasta_nao_chega_na_burnwood(admin_logado, falsa, caminho):
    assert admin_logado.get(f"{ROTA}/{caminho}").status_code == 404
    assert _repasses(falsa) == []


# ---------------------------------------------------------------- o repasse


def teste_lista_repassa_com_key_operador_e_slug(admin_logado, administrador, falsa):
    falsa.responder("GET", "/v1/tenants/vip-import/conversations", corpo={"items": [], "next_cursor": None})

    resposta = admin_logado.get(f"{ROTA}/conversations", params={"limit": "50", "state": ["bot_active", "paused"], "senha": "x"})

    assert resposta.status_code == 200
    assert resposta.json() == {"items": [], "next_cursor": None}
    [repasse] = _repasses(falsa)
    assert repasse.headers["Authorization"] == f"Bearer {KEY}"
    assert repasse.headers["X-Burnwood-Operator"] == administrador.nome
    # Parâmetros fora da lista caem; os repetidos passam todos.
    assert repasse.url.params.get_list("state") == ["bot_active", "paused"]
    assert repasse.url.params.get("limit") == "50"
    assert "senha" not in repasse.url.params


def teste_resposta_volta_para_o_painel_sem_a_key(admin_logado, falsa):
    falsa.responder("GET", f"/v1/tenants/vip-import/conversations/{CONVERSA}", corpo={"id": CONVERSA})
    resposta = admin_logado.get(f"{ROTA}/conversations/{CONVERSA}")
    assert resposta.status_code == 200
    assert KEY not in resposta.text


def teste_responder_repassa_o_corpo(admin_logado, falsa):
    caminho = f"/v1/tenants/vip-import/conversations/{CONVERSA}/reply"
    falsa.responder("POST", caminho, corpo={"id": "m1", "body": "Oi!"})

    resposta = admin_logado.post(f"{ROTA}/conversations/{CONVERSA}/reply", json={"body": "Oi!"})

    assert resposta.status_code == 200
    [repasse] = _repasses(falsa)
    assert json.loads(repasse.content) == {"body": "Oi!"}
    assert repasse.headers["Content-Type"] == "application/json"


def teste_acao_sem_corpo_manda_objeto_vazio(admin_logado, falsa):
    falsa.responder("POST", f"/v1/tenants/vip-import/conversations/{CONVERSA}/takeover", status=204)

    resposta = admin_logado.post(f"{ROTA}/conversations/{CONVERSA}/takeover")

    # Nenhuma rota desta API devolve 204.
    assert resposta.status_code == 200
    assert resposta.json() == {"ok": True}
    [repasse] = _repasses(falsa)
    assert repasse.content == b"{}"


def teste_erro_da_burnwood_vira_envelope_da_api(admin_logado, falsa):
    falsa.responder(
        "POST",
        f"/v1/tenants/vip-import/conversations/{CONVERSA}/takeover",
        status=409,
        corpo={"error": {"code": "conversation_assigned", "message": "Already assigned"}},
    )

    resposta = admin_logado.post(f"{ROTA}/conversations/{CONVERSA}/takeover")

    assert resposta.status_code == 409
    assert resposta.json()["erro"] == {
        "codigo": "CONVERSATION_ASSIGNED",
        "mensagem": "Outra pessoa já assumiu esta conversa.",
    }


def teste_nome_do_operador_sem_quebra_de_linha_e_curto():
    assert burnwood.nome_do_operador("Ana\r\nX-Outro: 1") == "AnaX-Outro: 1"
    assert len(burnwood.nome_do_operador("a" * 300)) == 100
    assert burnwood.nome_do_operador("\n") == "Equipe VIP Imports"


# ---------------------------------------------------------------- desligado


def teste_sem_key_o_painel_recebe_503(admin_logado, falsa, monkeypatch):
    monkeypatch.setattr(configuracao, "BURNWOOD_API_KEY", "")
    resposta = admin_logado.get(f"{ROTA}/conversations")
    assert resposta.status_code == 503
    assert resposta.json()["erro"]["codigo"] == "ATENDIMENTO_INDISPONIVEL"
    assert falsa.chamadas == []


def teste_burnwood_fora_do_ar_o_painel_recebe_503(admin_logado, falsa):
    falsa.fora_do_ar = True
    resposta = admin_logado.get(f"{ROTA}/conversations")
    assert resposta.status_code == 503
    assert resposta.json()["erro"]["codigo"] == "ATENDIMENTO_INDISPONIVEL"


# ---------------------------------------------------------------- widget


def teste_widget_usa_o_canal_com_agente(sem_sessao, falsa):
    resposta = sem_sessao.get("/api/v1/atendimento/widget")
    assert resposta.status_code == 200
    assert resposta.json() == {"widgetUrl": "https://dev.burnwood.com.br", "chaveCanal": "wk_com_agente"}
    assert KEY not in resposta.text


def teste_widget_respeita_o_canal_escolhido(sem_sessao, falsa, monkeypatch):
    monkeypatch.setattr(configuracao, "BURNWOOD_CHANNEL_KEY", "wk_sem_agente")
    assert sem_sessao.get("/api/v1/atendimento/widget").json()["chaveCanal"] == "wk_sem_agente"


def teste_widget_desligado_sem_key(sem_sessao, falsa, monkeypatch):
    monkeypatch.setattr(configuracao, "BURNWOOD_API_KEY", "")
    resposta = sem_sessao.get("/api/v1/atendimento/widget")
    assert resposta.status_code == 200
    assert resposta.json() == {"widgetUrl": None, "chaveCanal": None}
    assert falsa.chamadas == []


def teste_widget_desligado_com_burnwood_fora_do_ar(sem_sessao, falsa):
    falsa.fora_do_ar = True
    resposta = sem_sessao.get("/api/v1/atendimento/widget")
    assert resposta.status_code == 200
    assert resposta.json() == {"widgetUrl": None, "chaveCanal": None}


def teste_widget_fica_atras_do_portao(sem_sessao, sessao, falsa):
    """Loja fechada: quem ainda não entrou não recebe o chat (o agente conhece o catálogo)."""
    sessao.get(AcessoConfig, 1).modo = "aprovacao"
    sessao.commit()
    resposta = sem_sessao.get("/api/v1/atendimento/widget")
    assert resposta.status_code == sem_sessao.get("/api/v1/home").status_code == 401
    assert "wk_" not in resposta.text


@pytest.mark.parametrize(
    "api, widget",
    [
        ("https://api.dev.burnwood.com.br", "https://dev.burnwood.com.br"),
        ("https://api.staging.burnwood.com.br", "https://staging.burnwood.com.br"),
        ("https://api.burnwood.com.br", "https://app.burnwood.com.br"),
        ("http://localhost:9000", "http://localhost:9000"),
    ],
)
def teste_url_do_widget(api, widget):
    assert burnwood.url_do_widget(api) == widget
