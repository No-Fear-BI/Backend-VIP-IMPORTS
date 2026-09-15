"""As três regras de colisão do `POST /carrinho/migrar`.

Herdado do passo `migracao` do antigo roteiro de verificação da Fatia 3. O que
está em jogo é a venda: se o carrinho montado como visitante esvaziar na hora da
identificação, a pessoa desiste. Por isso item que não dá para migrar volta em
`ignorados`, e não some em silêncio.

Regra 1: mesmo produto e mesmo PAR de variações -> não duplica.
Regra 2: mesmo produto e par diferente -> dois itens.
Regra 3: produto oculto ou inexistente -> `ignorados`, com o motivo.
"""

from sqlalchemy import select

from vip_api.modelos.catalogo import ProdutoVariacao


def variacoes(sessao, produto):
    tamanho = sessao.scalar(
        select(ProdutoVariacao.id).where(
            ProdutoVariacao.produto_id == produto.id, ProdutoVariacao.tipo == "tamanho"
        )
    )
    cor = sessao.scalar(
        select(ProdutoVariacao.id).where(
            ProdutoVariacao.produto_id == produto.id, ProdutoVariacao.tipo == "cor"
        )
    )
    return tamanho, cor


def teste_mesmo_par_nao_duplica(cliente_logado, sessao, produto_com_variacoes):
    tamanho, cor = variacoes(sessao, produto_com_variacoes)
    item = {
        "produtoId": produto_com_variacoes.id,
        "variacaoTamanhoId": tamanho,
        "variacaoCorId": cor,
    }
    cliente_logado.post("/api/v1/carrinho", json=item)

    resposta = cliente_logado.post("/api/v1/carrinho/migrar", json={"itens": [item]})

    assert resposta.status_code == 200
    assert len(resposta.json()["itens"]) == 1
    assert resposta.json()["ignorados"] == []


def teste_par_diferente_vira_outro_item(cliente_logado, sessao, produto_com_variacoes):
    tamanho, cor = variacoes(sessao, produto_com_variacoes)
    cliente_logado.post(
        "/api/v1/carrinho",
        json={
            "produtoId": produto_com_variacoes.id,
            "variacaoTamanhoId": tamanho,
            "variacaoCorId": cor,
        },
    )

    resposta = cliente_logado.post(
        "/api/v1/carrinho/migrar",
        json={
            "itens": [
                # O par completo já está na conta: não duplica.
                {
                    "produtoId": produto_com_variacoes.id,
                    "variacaoTamanhoId": tamanho,
                    "variacaoCorId": cor,
                },
                # Só o tamanho, e só a cor: dois pares diferentes do primeiro.
                {"produtoId": produto_com_variacoes.id, "variacaoTamanhoId": tamanho},
                {"produtoId": produto_com_variacoes.id, "variacaoCorId": cor},
            ]
        },
    )

    assert resposta.status_code == 200
    itens = resposta.json()["itens"]
    assert len(itens) == 3
    pares = {
        (
            (item["variacaoTamanho"] or {}).get("id"),
            (item["variacaoCor"] or {}).get("id"),
        )
        for item in itens
    }
    assert pares == {(tamanho, cor), (tamanho, None), (None, cor)}


def teste_produto_oculto_e_inexistente_voltam_em_ignorados(
    cliente_logado, sessao, catalogo
):
    oculto = catalogo.ocultos[0]
    visivel = catalogo.visiveis[0]

    resposta = cliente_logado.post(
        "/api/v1/carrinho/migrar",
        json={
            "itens": [
                {"produtoId": visivel.id},
                {"produtoId": oculto.id},
                {"produtoId": 99_999_999},
            ]
        },
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert [item["id"] for item in corpo["itens"]] == [visivel.id]

    motivos = {item["produtoId"]: item["motivo"] for item in corpo["ignorados"]}
    assert motivos == {
        oculto.id: "PRODUTO_INDISPONIVEL",
        99_999_999: "PRODUTO_NAO_ENCONTRADO",
    }
    # A mensagem vai pronta para a tela dizer "2 itens não estão mais
    # disponíveis" em vez de sumir com eles.
    assert all(item["mensagem"] for item in corpo["ignorados"])


def teste_migracao_de_item_invalido_nao_derruba_os_validos(
    cliente_logado, sessao, produto_com_variacoes, catalogo
):
    """Uma transação só, mas falha de um item não é falha da migração: o que
    dá para migrar, migra."""
    tamanho, _ = variacoes(sessao, produto_com_variacoes)

    resposta = cliente_logado.post(
        "/api/v1/carrinho/migrar",
        json={
            "itens": [
                {"produtoId": produto_com_variacoes.id, "variacaoTamanhoId": tamanho},
                {"produtoId": catalogo.ocultos[0].id},
            ]
        },
    )

    assert resposta.status_code == 200
    assert len(resposta.json()["itens"]) == 1
    assert len(resposta.json()["ignorados"]) == 1
