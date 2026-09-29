"""Filtro GET /produtos?novidades=true: produto fica no máximo 14 dias em Novidades.

O "agora" da janela é fixado (`_agora` do serviço), e cada produto nasce com
`criado_em` relativo a ele. Sem isso o teste flutuaria no limite dos 14 dias.
Os produtos daqui são só os deste teste: cada teste roda na sua transação.
"""

from datetime import datetime, timedelta, timezone

import pytest

from vip_api.servicos import catalogo as servico_catalogo
from vip_api.servicos.catalogo import DIAS_NOVIDADE

from testes.fabrica import criar_categoria, criar_marca, criar_produto

AGORA = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)
URL = "/api/v1/produtos"


@pytest.fixture(autouse=True)
def relogio_fixo(monkeypatch):
    monkeypatch.setattr(servico_catalogo, "_agora", lambda: AGORA)


@pytest.fixture
def massa(sessao):
    marca = criar_marca(sessao, "Chanel", "chanel", 1)
    outra_marca = criar_marca(sessao, "Gucci", "gucci", 2)
    bolsas = criar_categoria(sessao, "feminino", "Bolsas", "bolsas")
    sapatos = criar_categoria(sessao, "masculino", "Sapatos", "sapatos")

    def novo(codigo, nome, dias, categoria=bolsas, marca_=marca, status="normal"):
        produto = criar_produto(sessao, codigo, nome, marca_, categoria, status=status)
        produto.criado_em = AGORA - timedelta(days=dias)
        sessao.flush()
        return produto

    dados = {
        "marca": marca,
        "bolsas": bolsas,
        "recente": novo("NOV-013", "Bolsa Recente", 13),
        "antigo": novo("NOV-015", "Bolsa Antiga", 15),
        "oculto": novo("NOV-OCU", "Bolsa Oculta Recente", 1, status="oculto"),
        "sapato_recente": novo("NOV-SAP", "Sapato Recente", 2, categoria=sapatos, marca_=outra_marca),
        "sapato_antigo": novo("NOV-SAA", "Sapato Antigo", 40, categoria=sapatos, marca_=outra_marca),
    }
    sessao.commit()
    return dados


def _ids(resposta) -> set[int]:
    assert resposta.status_code == 200, resposta.text
    return {item["id"] for item in resposta.json()["dados"]}


def teste_a_janela_e_de_14_dias():
    assert DIAS_NOVIDADE == 14


def teste_13_dias_entra_e_15_dias_nao(sem_sessao, massa):
    ids = _ids(sem_sessao.get(URL, params={"novidades": "true"}))
    assert massa["recente"].id in ids
    assert massa["antigo"].id not in ids
    assert massa["sapato_recente"].id in ids
    assert massa["sapato_antigo"].id not in ids


def teste_o_limite_de_14_dias_inclui_o_de_exatamente_14(sem_sessao, sessao, massa):
    limite = criar_produto(
        sessao, "NOV-014", "Bolsa No Limite", massa["marca"], massa["bolsas"]
    )
    limite.criado_em = AGORA - timedelta(days=DIAS_NOVIDADE)
    sessao.commit()
    assert limite.id in _ids(sem_sessao.get(URL, params={"novidades": "true"}))


def teste_produto_de_15_dias_continua_em_todos_lugares_sem_o_filtro(sem_sessao, massa):
    antigo = massa["antigo"].id

    assert antigo in _ids(sem_sessao.get(URL))
    assert antigo in _ids(sem_sessao.get(URL, params={"novidades": "false"}))
    assert antigo in _ids(sem_sessao.get(URL, params={"colecao": "feminino", "categoria": "bolsas"}))
    assert antigo in _ids(sem_sessao.get(URL, params={"colecao": "feminino"}))
    assert antigo in _ids(sem_sessao.get(URL, params={"marca": "chanel"}))
    assert antigo in _ids(sem_sessao.get(URL, params={"busca": "antiga"}))
    assert antigo in _ids(sem_sessao.get(URL, params={"busca": "NOV-015"}))


def teste_false_e_ausente_dao_a_mesma_lista(sem_sessao, massa):
    assert _ids(sem_sessao.get(URL)) == _ids(sem_sessao.get(URL, params={"novidades": "false"}))


def teste_oculto_recente_nao_aparece(sem_sessao, massa):
    assert massa["oculto"].id not in _ids(sem_sessao.get(URL, params={"novidades": "true"}))


def teste_combina_com_colecao_categoria_marca_e_busca(sem_sessao, massa):
    def com(**filtros):
        return _ids(sem_sessao.get(URL, params={"novidades": "true", **filtros}))

    assert com(colecao="feminino") == {massa["recente"].id}
    assert com(colecao="masculino") == {massa["sapato_recente"].id}
    assert com(colecao="feminino", categoria="bolsas") == {massa["recente"].id}
    assert com(colecao="feminino", categoria="sapatos") == set()
    assert com(marca="gucci") == {massa["sapato_recente"].id}
    assert com(busca="bolsa") == {massa["recente"].id}
    # Busca por código exato respeita a janela: o antigo não volta por esse atalho.
    assert com(busca="NOV-013") == {massa["recente"].id}
    assert com(busca="NOV-015") == set()


def teste_combina_com_a_ordem(sem_sessao, massa):
    resposta = sem_sessao.get(URL, params={"novidades": "true", "ordem": "nome"})
    nomes = [item["nome"] for item in resposta.json()["dados"]]
    assert nomes == sorted(nomes)
    assert len(nomes) == 2


def _percorrer(http, **filtros) -> tuple[list[int], list[int]]:
    ids, totais, cursor = [], [], None
    for _ in range(50):
        parametros = {"porPagina": 3, **filtros}
        if cursor:
            parametros["cursor"] = cursor
        resposta = http.get(URL, params=parametros)
        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        ids.extend(item["id"] for item in corpo["dados"])
        totais.append(corpo["paginacao"]["total"])
        cursor = corpo["paginacao"].get("proximoCursor")
        if not cursor:
            return ids, totais
    raise AssertionError("paginação não terminou")


@pytest.fixture
def muitas(sessao, massa):
    """10 recentes a mais (todos com dias diferentes) e 5 antigos."""
    marca, categoria = massa["marca"], massa["bolsas"]
    recentes = []
    for i in range(10):
        produto = criar_produto(sessao, f"PAG-R{i:02d}", f"Peça Recente {i}", marca, categoria)
        produto.criado_em = AGORA - timedelta(hours=6 * (i + 1))
        recentes.append(produto.id)
    for i in range(5):
        produto = criar_produto(sessao, f"PAG-A{i:02d}", f"Peça Antiga {i}", marca, categoria)
        produto.criado_em = AGORA - timedelta(days=20 + i)
    sessao.commit()
    return recentes


@pytest.mark.parametrize("ordem", ["recentes", "nome"])
def teste_paginacao_com_cursor_dentro_das_novidades(sem_sessao, massa, muitas, ordem):
    ids, totais = _percorrer(sem_sessao, novidades="true", ordem=ordem)

    esperados = set(muitas) | {massa["recente"].id, massa["sapato_recente"].id}
    assert len(ids) == len(set(ids)), "item repetido entre páginas"
    assert set(ids) == esperados
    assert len(totais) > 1, "a paginação precisava ter mais de uma página"
    assert set(totais) == {len(esperados)}


def teste_cursor_de_novidades_nao_vale_sem_o_filtro_e_vice_versa(sem_sessao, massa, muitas):
    com = sem_sessao.get(URL, params={"novidades": "true", "porPagina": 3}).json()
    sem = sem_sessao.get(URL, params={"porPagina": 3}).json()

    cursor_com = com["paginacao"]["proximoCursor"]
    cursor_sem = sem["paginacao"]["proximoCursor"]

    for filtros in (
        {"cursor": cursor_com},
        {"cursor": cursor_com, "novidades": "false"},
        {"cursor": cursor_sem, "novidades": "true"},
    ):
        resposta = sem_sessao.get(URL, params={"porPagina": 3, **filtros})
        assert resposta.status_code == 400, filtros
        assert resposta.json()["erro"]["codigo"] == "CURSOR_INVALIDO"


@pytest.mark.parametrize("valor", ["talvez", "1", "sim", "TRUE", ""])
def teste_valor_invalido_da_400(sem_sessao, massa, valor):
    resposta = sem_sessao.get(URL, params={"novidades": valor})
    assert resposta.status_code == 400
