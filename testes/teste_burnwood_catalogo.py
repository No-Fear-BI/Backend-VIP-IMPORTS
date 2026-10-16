"""GET /burnwood/catalogo: a consulta que o agente da Burnwood faz ao responder no chat.

O que importa: token obrigatório, busca por palavra (a pergunta do cliente vem picada em
poucas palavras), só o que a loja mostra mais o preço, e nunca escrever nada.
"""

import pytest
from sqlalchemy import func, select

from testes.fabrica import criar_categoria, criar_marca, criar_produto
from vip_api.configuracao import configuracao
from vip_api.modelos.acesso import AcessoConfig
from vip_api.modelos.catalogo import Produto
from vip_api.servicos.burnwood_catalogo import palavras_da_busca

ROTA = "/api/v1/burnwood/catalogo"
TOKEN = "t" * 48
CABECALHO = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture(autouse=True)
def token_e_loja(monkeypatch):
    monkeypatch.setattr(configuracao, "BURNWOOD_CATALOGO_TOKEN", TOKEN)
    monkeypatch.setattr(configuracao, "LOJA_URL", "https://loja.test")


@pytest.fixture
def catalogo_burnwood(sessao):
    nike = criar_marca(sessao, "Nike", "nike")
    lacoste = criar_marca(sessao, "Lacoste", "lacoste")
    tenis = criar_categoria(sessao, "masculino", "Tênis", "tenis")
    camisetas = criar_categoria(sessao, "masculino", "Camisetas", "camisetas")
    af1 = criar_produto(
        sessao, "AF1-0042", "Tênis Air Force 1", nike, tenis,
        variacoes=[("tamanho", "39"), ("tamanho", "40"), ("tamanho", "42"), ("cor", "Branco")],
    )
    af1.preco_centavos = 79990
    af1.quantidade_disponivel = 4
    af1.origem_url = "https://fornecedor.test/album/1"
    preto = criar_produto(
        sessao, "AF1-0043", "Tênis Air Force 1", nike, tenis,
        variacoes=[("tamanho", "42"), ("cor", "Preto")],
    )
    preto.status = "esgotado"
    criar_produto(sessao, "POL-0001", "Camiseta Polo", lacoste, camisetas, variacoes=[("tamanho", "M")])
    oculto = criar_produto(sessao, "AF1-0099", "Tênis Air Force 1 Oculto", nike, tenis)
    oculto.status = "oculto"
    sessao.commit()
    return af1


# ---------------------------------------------------------------- token


@pytest.mark.parametrize(
    "cabecalho",
    [{}, {"Authorization": "Bearer errado"}, {"Authorization": TOKEN}, {"Authorization": f"Bearer {TOKEN}x"}],
)
def teste_sem_o_token_certo_e_401(sem_sessao, catalogo_burnwood, cabecalho):
    resposta = sem_sessao.get(ROTA, params={"q": "air force"}, headers=cabecalho, follow_redirects=False)
    assert resposta.status_code == 401
    assert "AF1" not in resposta.text


def teste_token_vazio_na_configuracao_desliga_a_consulta(sem_sessao, catalogo_burnwood, monkeypatch):
    monkeypatch.setattr(configuracao, "BURNWOOD_CATALOGO_TOKEN", "")
    assert sem_sessao.get(ROTA, params={"q": "air"}, headers={"Authorization": "Bearer "}).status_code == 401


def teste_funciona_com_a_loja_fechada_e_sem_sessao(sem_sessao, sessao, catalogo_burnwood):
    """Quem chama é o servidor da Burnwood: não tem sessão nem passa pelo portão."""
    sessao.get(AcessoConfig, 1).modo = "aprovacao"
    sessao.commit()
    assert sem_sessao.get(ROTA, params={"q": "air"}, headers=CABECALHO).status_code == 200


# ---------------------------------------------------------------- busca


def teste_busca_por_palavra_acha_pelo_nome_cor_e_tamanho(sem_sessao, catalogo_burnwood):
    resposta = sem_sessao.get(ROTA, params={"q": "air force branco 42"}, headers=CABECALHO)

    assert resposta.status_code == 200
    itens = resposta.json()["items"]
    # O branco casa as quatro palavras e vem primeiro; o preto casa três; a polo, nenhuma.
    assert [i["sku"] for i in itens] == ["AF1-0042", "AF1-0043"]


def teste_formato_do_item(sem_sessao, catalogo_burnwood):
    [item, *_] = sem_sessao.get(ROTA, params={"q": "air force"}, headers=CABECALHO).json()["items"]
    assert item == {
        "sku": "AF1-0042",
        "nome": "Tênis Air Force 1",
        "marca": "Nike",
        "categoria": "Tênis",
        "publico": "Masculina",
        "preco": 799.9,
        "disponivel": True,
        "estoque": 4,
        "tamanhos": ["39", "40", "42"],
        "cores": ["Branco"],
        "link": "https://loja.test/produto/AF1-0042",
    }


def teste_esgotado_vem_marcado_e_depois_do_disponivel(sem_sessao, catalogo_burnwood):
    itens = sem_sessao.get(ROTA, params={"q": "air force"}, headers=CABECALHO).json()["items"]
    assert [(i["sku"], i["disponivel"]) for i in itens] == [("AF1-0042", True), ("AF1-0043", False)]
    assert itens[1]["preco"] is None and itens[1]["estoque"] is None


def teste_oculto_nunca_aparece(sem_sessao, catalogo_burnwood):
    itens = sem_sessao.get(ROTA, params={"q": "oculto"}, headers=CABECALHO).json()["items"]
    assert itens == []


@pytest.mark.parametrize("q", ["", "de a o", "xyzzy inexistente"])
def teste_sem_resultado_e_lista_vazia(sem_sessao, catalogo_burnwood, q):
    resposta = sem_sessao.get(ROTA, params={"q": q}, headers=CABECALHO)
    assert resposta.status_code == 200
    assert resposta.json() == {"items": []}


def teste_acha_pela_marca_categoria_e_codigo(sem_sessao, catalogo_burnwood):
    def skus(q):
        return [i["sku"] for i in sem_sessao.get(ROTA, params={"q": q}, headers=CABECALHO).json()["items"]]

    assert skus("lacoste") == ["POL-0001"]
    assert skus("camisetas") == ["POL-0001"]
    # O código exato vem primeiro; o irmão "AF1-…" casa só pela parte "af1".
    assert skus("af1-0043")[0] == "AF1-0043"
    assert "AF1-0042" not in skus("42 polo")[:1]


def teste_respeita_o_limite(sem_sessao, catalogo_burnwood):
    itens = sem_sessao.get(ROTA, params={"q": "air", "limit": 1}, headers=CABECALHO).json()["items"]
    assert len(itens) == 1
    assert sem_sessao.get(ROTA, params={"q": "air", "limit": 500}, headers=CABECALHO).status_code == 400


def teste_nada_interno_sai(sem_sessao, catalogo_burnwood):
    texto = sem_sessao.get(ROTA, params={"q": "air force"}, headers=CABECALHO).text
    assert "fornecedor.test" not in texto
    for campo in ("origem", "custo", "fornecedor", "precoCentavos", "preco_centavos", "email"):
        assert campo not in texto


def teste_so_leitura(sem_sessao, sessao, catalogo_burnwood):
    antes = sessao.scalar(select(func.count()).select_from(Produto))
    for metodo in ("POST", "PUT", "PATCH", "DELETE"):
        assert sem_sessao.request(metodo, ROTA, headers=CABECALHO).status_code == 405
    sem_sessao.get(ROTA, params={"q": "air"}, headers=CABECALHO)
    assert sessao.scalar(select(func.count()).select_from(Produto)) == antes


def teste_palavras_da_busca():
    assert palavras_da_busca("Tênis Air-Force, branco 42!") == ["tenis", "air", "force", "branco", "42"]
    assert palavras_da_busca("tem a camiseta polo no tamanho M?") == ["camiseta", "polo"]
    assert palavras_da_busca("air air air") == ["air"]
