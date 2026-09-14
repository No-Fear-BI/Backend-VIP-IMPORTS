"""Variações do painel (tarefa 56) e as TRÊS portas da armadilha do carrinho.

A armadilha: `carrinho_itens` aponta para `produto_variacoes` com
`ON DELETE SET NULL`, e a unicidade do item é (carrinho, produto, tamanho, cor)
com NULLS NOT DISTINCT. Apagar uma variação zera a coluna nos itens que a
usavam, e o item que vira (nulo, nulo) colide com outro item do mesmo produto
no mesmo carrinho. Deu 500 de verdade, ao excluir um produto do catálogo de
desenvolvimento.

Os três testes marcados como PORTA são a regressão — cada um foi conferido
falhando com a correção desligada.
"""

import pytest
from sqlalchemy import select

from testes.fabrica import criar_categoria, criar_marca, criar_produto
from vip_api.modelos.catalogo import Produto, ProdutoVariacao
from vip_api.modelos.cliente import CarrinhoItem

ROTA = "/api/v1/admin/produtos"


@pytest.fixture
def produto_com_grade(sessao):
    """Um produto com dois tamanhos e duas cores — grade suficiente para os
    itens de carrinho colidirem de mais de um jeito."""
    marca = criar_marca(sessao, "Chanel", "chanel")
    categoria = criar_categoria(sessao, "feminino", "Bolsas", "bolsas")
    produto = criar_produto(
        sessao,
        codigo="CHN-5000",
        nome="Bolsa da Grade",
        marca=marca,
        categoria=categoria,
        variacoes=[("tamanho", "M"), ("tamanho", "G"), ("cor", "Preto"), ("cor", "Bege")],
    )
    sessao.commit()
    return produto


def variacoes_por_valor(sessao, produto_id) -> dict[str, int]:
    return {
        f"{v.tipo}:{v.valor}": v.id
        for v in sessao.scalars(
            select(ProdutoVariacao).where(ProdutoVariacao.produto_id == produto_id)
        )
    }


def itens_do_carrinho(sessao, produto_id) -> list[tuple[int, int | None, int | None]]:
    return [
        (item.id, item.variacao_tamanho_id, item.variacao_cor_id)
        for item in sessao.scalars(
            select(CarrinhoItem)
            .where(CarrinhoItem.produto_id == produto_id)
            .order_by(CarrinhoItem.id)
        )
    ]


# ======================================================================
# As três portas
# ======================================================================


def teste_porta_1_excluir_o_produto(admin_logado, cliente_logado, sessao, produto_com_grade):
    """PORTA 1 — `DELETE /admin/produtos/:id`.

    Dois itens no mesmo carrinho: um com tamanho, outro sem variação nenhuma.
    Apagar o produto apaga as variações, e o primeiro item viraria (nulo, nulo)
    em cima do segundo.
    """
    ids = variacoes_por_valor(sessao, produto_com_grade.id)
    cliente_logado.post(
        "/api/v1/carrinho",
        json={"produtoId": produto_com_grade.id, "variacaoTamanhoId": ids["tamanho:M"]},
    )
    cliente_logado.post("/api/v1/carrinho", json={"produtoId": produto_com_grade.id})
    assert len(cliente_logado.get("/api/v1/carrinho").json()) == 2

    resposta = admin_logado.delete(f"{ROTA}/{produto_com_grade.id}")

    assert resposta.status_code == 200
    sessao.expire_all()
    assert sessao.get(Produto, produto_com_grade.id) is None
    assert cliente_logado.get("/api/v1/carrinho").json() == []


def teste_porta_2_tirar_uma_variacao_da_lista(
    admin_logado, cliente_logado, sessao, produto_com_grade
):
    """PORTA 2 — uma variação sai, as outras ficam.

    O item que usava o tamanho M vira (nulo, Preto) e cai em cima do item que
    já era (nulo, Preto). Os dois viram um: some o que estava sendo mexido e
    fica o que já ocupava o par — a mesma regra da troca de variação feita pelo
    cliente.
    """
    ids = variacoes_por_valor(sessao, produto_com_grade.id)
    cliente_logado.post(
        "/api/v1/carrinho",
        json={
            "produtoId": produto_com_grade.id,
            "variacaoTamanhoId": ids["tamanho:M"],
            "variacaoCorId": ids["cor:Preto"],
        },
    )
    cliente_logado.post(
        "/api/v1/carrinho",
        json={"produtoId": produto_com_grade.id, "variacaoCorId": ids["cor:Preto"]},
    )
    antes = itens_do_carrinho(sessao, produto_com_grade.id)
    assert len(antes) == 2
    # O segundo item é o que já estava em (nulo, Preto) — é ele que sobrevive.
    ja_ocupava_o_par = antes[1][0]

    resposta = admin_logado.patch(
        f"{ROTA}/{produto_com_grade.id}/variacoes",
        json={
            "variacoes": [
                # "M" sai da lista; o resto permanece.
                {"tipo": "tamanho", "valor": "G"},
                {"tipo": "cor", "valor": "Preto"},
                {"tipo": "cor", "valor": "Bege"},
            ]
        },
    )

    assert resposta.status_code == 200
    assert "M" not in [v["valor"] for v in resposta.json()]

    sessao.expire_all()
    depois = itens_do_carrinho(sessao, produto_com_grade.id)
    assert len(depois) == 1
    assert depois[0][0] == ja_ocupava_o_par
    assert depois[0][1] is None
    assert depois[0][2] == ids["cor:Preto"]


def teste_porta_3_substituir_o_conjunto_com_dois_carrinhos(
    admin_logado, cliente_logado, outro_cliente_logado, sessao, produto_com_grade
):
    """PORTA 3 — a pior: várias variações saem de uma vez e a colisão acontece
    em carrinhos de clientes DIFERENTES, na mesma transação."""
    ids = variacoes_por_valor(sessao, produto_com_grade.id)

    for http in (cliente_logado, outro_cliente_logado):
        http.post(
            "/api/v1/carrinho",
            json={
                "produtoId": produto_com_grade.id,
                "variacaoTamanhoId": ids["tamanho:M"],
                "variacaoCorId": ids["cor:Bege"],
            },
        )
        http.post(
            "/api/v1/carrinho",
            json={"produtoId": produto_com_grade.id, "variacaoTamanhoId": ids["tamanho:M"]},
        )
    assert len(itens_do_carrinho(sessao, produto_com_grade.id)) == 4

    resposta = admin_logado.patch(
        f"{ROTA}/{produto_com_grade.id}/variacoes",
        # Só o tamanho M sobrevive; as duas cores e o G saem juntos.
        json={"variacoes": [{"tipo": "tamanho", "valor": "M"}]},
    )

    assert resposta.status_code == 200
    assert [(v["tipo"], v["valor"]) for v in resposta.json()] == [("tamanho", "M")]

    sessao.expire_all()
    # Um item por cliente: os dois de cada um viraram o mesmo par (M, nulo).
    depois = itens_do_carrinho(sessao, produto_com_grade.id)
    assert len(depois) == 2
    assert {item[1] for item in depois} == {ids["tamanho:M"]}
    assert {item[2] for item in depois} == {None}
    assert len(cliente_logado.get("/api/v1/carrinho").json()) == 1
    assert len(outro_cliente_logado.get("/api/v1/carrinho").json()) == 1


# ======================================================================
# Comportamento de PATCH /variacoes
# ======================================================================


def teste_o_que_permanece_mantem_o_id(admin_logado, sessao, produto_com_grade):
    """Reaproveitar o id é o que salva o carrinho de quem já tinha escolhido:
    recriar a mesma variação com id novo zeraria a escolha pelo SET NULL."""
    antes = variacoes_por_valor(sessao, produto_com_grade.id)

    resposta = admin_logado.patch(
        f"{ROTA}/{produto_com_grade.id}/variacoes",
        json={
            "variacoes": [
                {"tipo": "tamanho", "valor": "M"},
                {"tipo": "tamanho", "valor": "GG"},
                {"tipo": "cor", "valor": "Preto", "disponivel": False},
            ]
        },
    )

    assert resposta.status_code == 200
    depois = {f"{v['tipo']}:{v['valor']}": v["id"] for v in resposta.json()}
    assert depois["tamanho:M"] == antes["tamanho:M"]
    assert depois["cor:Preto"] == antes["cor:Preto"]
    assert depois["tamanho:GG"] not in antes.values()
    assert "tamanho:G" not in depois and "cor:Bege" not in depois
    assert [v for v in resposta.json() if v["valor"] == "Preto"][0]["disponivel"] is False


def teste_escolha_do_cliente_sobrevive_ao_salvamento(
    admin_logado, cliente_logado, sessao, produto_com_grade
):
    ids = variacoes_por_valor(sessao, produto_com_grade.id)
    cliente_logado.post(
        "/api/v1/carrinho",
        json={
            "produtoId": produto_com_grade.id,
            "variacaoTamanhoId": ids["tamanho:M"],
            "variacaoCorId": ids["cor:Preto"],
        },
    )

    admin_logado.patch(
        f"{ROTA}/{produto_com_grade.id}/variacoes",
        json={
            "variacoes": [
                {"tipo": "tamanho", "valor": "M"},
                {"tipo": "tamanho", "valor": "G"},
                {"tipo": "cor", "valor": "Preto"},
                {"tipo": "cor", "valor": "Bege"},
                {"tipo": "cor", "valor": "Vermelha"},
            ]
        },
    )

    (item,) = cliente_logado.get("/api/v1/carrinho").json()
    assert item["variacaoTamanho"]["valor"] == "M"
    assert item["variacaoCor"]["valor"] == "Preto"


def teste_lista_vazia_remove_todas(admin_logado, sessao, produto_com_grade):
    resposta = admin_logado.patch(
        f"{ROTA}/{produto_com_grade.id}/variacoes", json={"variacoes": []}
    )

    assert resposta.status_code == 200
    assert resposta.json() == []
    sessao.expire_all()
    assert variacoes_por_valor(sessao, produto_com_grade.id) == {}


def teste_valor_repetido_no_mesmo_tipo_responde_400(admin_logado, produto_com_grade):
    resposta = admin_logado.patch(
        f"{ROTA}/{produto_com_grade.id}/variacoes",
        json={
            "variacoes": [
                {"tipo": "tamanho", "valor": "M"},
                {"tipo": "tamanho", "valor": "M"},
            ]
        },
    )

    assert resposta.status_code == 400
    assert resposta.json()["erro"]["codigo"] == "DADOS_INVALIDOS"
    assert "variacoes" in resposta.json()["erro"]["campos"]


def teste_mesmo_valor_em_tipos_diferentes_e_aceito(admin_logado, produto_com_grade):
    """"Único" é por tipo: tamanho "Único" e cor "Único" são coisas diferentes,
    e o UNIQUE do banco é (produto, tipo, valor)."""
    resposta = admin_logado.patch(
        f"{ROTA}/{produto_com_grade.id}/variacoes",
        json={
            "variacoes": [
                {"tipo": "tamanho", "valor": "Único"},
                {"tipo": "cor", "valor": "Único"},
            ]
        },
    )

    assert resposta.status_code == 200
    assert len(resposta.json()) == 2


def teste_tipo_fora_do_enum_responde_400(admin_logado, produto_com_grade):
    resposta = admin_logado.patch(
        f"{ROTA}/{produto_com_grade.id}/variacoes",
        json={"variacoes": [{"tipo": "material", "valor": "Couro"}]},
    )

    assert resposta.status_code == 400
    assert resposta.json()["erro"]["codigo"] == "DADOS_INVALIDOS"


def teste_produto_inexistente_responde_404(admin_logado):
    resposta = admin_logado.patch(
        f"{ROTA}/99999/variacoes", json={"variacoes": [{"tipo": "cor", "valor": "Preto"}]}
    )

    assert resposta.status_code == 404
