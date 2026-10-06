"""O preço interno (`preco_centavos`, só do painel) NUNCA pode chegar à loja.

Duas travas independentes:

1. ESTRUTURAL — varre o OpenAPI de toda rota fora de `/admin` e falha se algum esquema de
   resposta alcançável tiver propriedade com cara de preço. Quem adicionar o campo a um esquema
   público reprova aqui, mesmo sem produto com preço no banco.
2. EM EXECUÇÃO — um produto COM preço (valor-sentinela) é lido por cada rota pública como cliente
   aprovado, e nenhuma chave nem o valor do preço podem aparecer no JSON.
"""

import json
import re

import pytest

from testes.fabrica import criar_categoria, criar_marca, criar_produto
from vip_api.principal import app

# Qualquer variação: preco, preço, price, pricing, centavos, custo, cost, brl, amount, reais.
# "valor" fica de fora de propósito: `variacoes[].valor` é o tamanho/a cor ("M", "Preto").
PADRAO_PRECO = re.compile(r"pre[cç]o|price|pricing|centavo|custo|cost|brl|amount|reais|monet", re.IGNORECASE)

SENTINELA_CENTAVOS = 123457  # R$ 1.234,57 — improvável de aparecer por acaso em outro campo
SENTINELAS_TEXTO = ("123457", "1234.57", "1234,57", "1.234,57")


def _propriedades_alcancaveis(esquema_raiz: dict, componentes: dict, vistos: set[str]):
    """Todo nome de propriedade de um esquema e dos que ele referencia (qualquer profundidade)."""
    if isinstance(esquema_raiz, dict):
        ref = esquema_raiz.get("$ref")
        if ref:
            nome = ref.rsplit("/", 1)[-1]
            if nome not in vistos:
                vistos.add(nome)
                yield from _propriedades_alcancaveis(componentes[nome], componentes, vistos)
        for chave, valor in esquema_raiz.items():
            if chave == "properties":
                for nome_prop, sub in valor.items():
                    yield nome_prop
                    yield from _propriedades_alcancaveis(sub, componentes, vistos)
            elif chave != "$ref":
                yield from _propriedades_alcancaveis(valor, componentes, vistos)
    elif isinstance(esquema_raiz, list):
        for item in esquema_raiz:
            yield from _propriedades_alcancaveis(item, componentes, vistos)


def teste_nenhum_esquema_publico_tem_campo_de_preco():
    openapi = app.openapi()
    componentes = openapi.get("components", {}).get("schemas", {})
    suspeitas = []
    for caminho, operacoes in openapi["paths"].items():
        if "/api/v1/admin" in caminho:
            continue
        for metodo, operacao in operacoes.items():
            # Só o que SAI: respostas. (Corpo de entrada não é vazamento.)
            for codigo, resposta in operacao.get("responses", {}).items():
                for nome in _propriedades_alcancaveis(resposta, componentes, set()):
                    if PADRAO_PRECO.search(nome):
                        suspeitas.append(f"{metodo.upper()} {caminho} [{codigo}] -> {nome}")
    assert not suspeitas, "Campo de preço em esquema PÚBLICO:\n" + "\n".join(sorted(set(suspeitas)))


def teste_o_campo_de_preco_so_existe_nos_esquemas_de_admin():
    """Sanidade da trava acima: o campo EXISTE em algum esquema de admin (se o padrão parasse de
    casar, a varredura passaria vazia sem proteger nada)."""
    openapi = app.openapi()
    componentes = openapi.get("components", {}).get("schemas", {})
    achou = False
    for caminho, operacoes in openapi["paths"].items():
        if "/api/v1/admin/produtos" not in caminho:
            continue
        for operacao in operacoes.values():
            for resposta in operacao.get("responses", {}).values():
                if any(PADRAO_PRECO.search(n) for n in _propriedades_alcancaveis(resposta, componentes, set())):
                    achou = True
    assert achou


def _chaves(valor):
    if isinstance(valor, dict):
        for chave, sub in valor.items():
            yield chave
            yield from _chaves(sub)
    elif isinstance(valor, list):
        for item in valor:
            yield from _chaves(item)


@pytest.fixture
def produto_com_preco(sessao, cliente_logado):
    marca = criar_marca(sessao, "Chanel", "chanel")
    categoria = criar_categoria(sessao, "feminino", "Bolsas", "bolsas")
    produto = criar_produto(
        sessao,
        codigo="TST-PRECO",
        nome="Bolsa Preço Secreto",
        marca=marca,
        categoria=categoria,
        variacoes=[("tamanho", "M"), ("cor", "Preto")],
    )
    produto.preco_centavos = SENTINELA_CENTAVOS
    produto.destaque = True
    produto.destaque_ordem = 1
    sessao.commit()
    return produto


def _conferir_limpo(resposta, rotulo):
    assert resposta.status_code in (200, 201), f"{rotulo}: {resposta.status_code} {resposta.text[:200]}"
    corpo = resposta.json()
    for chave in _chaves(corpo):
        assert not PADRAO_PRECO.search(chave), f"{rotulo}: chave de preço '{chave}' na resposta pública"
    texto = json.dumps(corpo, ensure_ascii=False)
    for sentinela in SENTINELAS_TEXTO:
        assert sentinela not in texto, f"{rotulo}: o valor do preço apareceu na resposta pública"


def teste_nenhuma_rota_publica_devolve_o_preco(cliente_logado, sessao, produto_com_preco):
    produto = produto_com_preco
    http = cliente_logado

    # Prova de que o produto tem o preço e que o painel o enxerga (senão o teste seria vazio).
    assert produto.preco_centavos == SENTINELA_CENTAVOS

    _conferir_limpo(http.get("/api/v1/produtos"), "listagem")
    _conferir_limpo(http.get(f"/api/v1/produtos/{produto.codigo}"), "detalhe")
    _conferir_limpo(http.get(f"/api/v1/produtos/{produto.codigo}/relacionados"), "relacionados")
    _conferir_limpo(http.get("/api/v1/produtos", params={"busca": "Secreto"}), "busca")
    _conferir_limpo(http.get("/api/v1/produtos", params={"novidades": "true"}), "novidades")
    _conferir_limpo(http.get("/api/v1/produtos", params={"ordem": "nome"}), "ordenacao")
    _conferir_limpo(http.get("/api/v1/home"), "home e destaques")
    _conferir_limpo(http.get("/api/v1/marcas"), "marcas")
    _conferir_limpo(http.get("/api/v1/colecoes"), "colecoes")

    # A listagem e a busca realmente trouxeram o produto (o teste olhou o que devia olhar).
    achados = http.get("/api/v1/produtos", params={"busca": "Secreto"}).json()["dados"]
    assert [p["codigo"] for p in achados] == [produto.codigo]

    # Favoritos, carrinho e seleção enviada.
    _conferir_limpo(http.post("/api/v1/favoritos", json={"produtoId": produto.id}), "favoritar")
    _conferir_limpo(http.get("/api/v1/favoritos"), "favoritos")
    from sqlalchemy import select

    from vip_api.modelos.catalogo import ProdutoVariacao

    tamanho = sessao.scalar(select(ProdutoVariacao.id).where(ProdutoVariacao.produto_id == produto.id, ProdutoVariacao.tipo == "tamanho"))
    cor = sessao.scalar(select(ProdutoVariacao.id).where(ProdutoVariacao.produto_id == produto.id, ProdutoVariacao.tipo == "cor"))
    _conferir_limpo(
        http.post("/api/v1/carrinho", json={"produtoId": produto.id, "variacaoTamanhoId": tamanho, "variacaoCorId": cor}),
        "adicionar ao carrinho",
    )
    _conferir_limpo(http.get("/api/v1/carrinho"), "carrinho")
    enviada = http.post("/api/v1/selecoes")
    _conferir_limpo(enviada, "enviar seleção")
    # O link do WhatsApp também não leva preço.
    assert not any(s in json.dumps(enviada.json()) for s in SENTINELAS_TEXTO)
    _conferir_limpo(http.get("/api/v1/selecoes"), "histórico de seleções")


def teste_o_painel_continua_vendo_o_preco(admin_logado, produto_com_preco):
    resposta = admin_logado.get(f"/api/v1/admin/produtos/{produto_com_preco.id}")
    assert resposta.status_code == 200
    assert resposta.json()["precoCentavos"] == SENTINELA_CENTAVOS
