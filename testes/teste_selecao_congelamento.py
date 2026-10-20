"""Enviar a seleção ao WhatsApp grava um pedido com a cópia do que o cliente viu.

Desde a migração 0021 o histórico de pedidos voltou (a 0019 o tinha removido). O
pedido é dado CONGELADO: o que o cliente viu e os dados dele ficam em texto, e
não mudam se o produto ou o cadastro mudarem depois.
"""

from urllib.parse import parse_qs, urlsplit

from sqlalchemy import func, select

from testes.fabrica import criar_categoria, criar_marca, criar_produto
from vip_api.modelos.catalogo import ProdutoVariacao
from vip_api.modelos.pedido import Pedido


def _adicionar(cliente_logado, sessao, produto) -> None:
    variacoes = {
        v.tipo: v.id
        for v in sessao.scalars(select(ProdutoVariacao).where(ProdutoVariacao.produto_id == produto.id))
    }
    resposta = cliente_logado.post(
        "/api/v1/carrinho",
        json={
            "produtoId": produto.id,
            "variacaoTamanhoId": variacoes.get("tamanho"),
            "variacaoCorId": variacoes.get("cor"),
        },
    )
    assert resposta.status_code == 200


def _total_de_pedidos(sessao) -> int:
    return sessao.scalar(select(func.count()).select_from(Pedido))


def teste_envio_grava_pedido_em_andamento(cliente_logado, cliente, sessao, produto_com_variacoes):
    _adicionar(cliente_logado, sessao, produto_com_variacoes)

    resposta = cliente_logado.post("/api/v1/selecoes")

    assert resposta.status_code == 200
    corpo = resposta.json()
    # A resposta ao cliente não mudou: só itens, mensagem e link.
    assert set(corpo) == {"itens", "mensagemWhatsapp", "linkWhatsapp"}
    assert "(Chanel, M / Preto)" in corpo["mensagemWhatsapp"]
    assert parse_qs(urlsplit(corpo["linkWhatsapp"]).query)["text"] == [corpo["mensagemWhatsapp"]]

    pedido = sessao.scalar(select(Pedido))
    assert pedido.status == "em_andamento"
    assert pedido.cliente_id == cliente.id
    assert pedido.cliente_email == cliente.email
    assert pedido.cliente_nome == cliente.nome
    assert pedido.total_itens == 1
    assert pedido.atualizado_em == pedido.criado_em
    [item] = pedido.itens
    assert (item.produto_codigo, item.produto_nome) == ("TST-PAR", "Bolsa Clássica Chanel")
    assert (item.marca_nome, item.variacao_tamanho, item.variacao_cor) == ("Chanel", "M", "Preto")
    # O carrinho NÃO é esvaziado: a seleção continua à mão.
    assert len(cliente_logado.get("/api/v1/carrinho").json()) == 1


def teste_pedido_nao_muda_quando_produto_e_cliente_mudam(
    cliente_logado, admin_logado, cliente, sessao, produto_com_variacoes
):
    _adicionar(cliente_logado, sessao, produto_com_variacoes)
    assert cliente_logado.post("/api/v1/selecoes").status_code == 200

    produto_com_variacoes.nome = "Nome Novo Da Bolsa"
    cliente.nome = "Nome Novo Do Cliente"
    sessao.commit()

    [pedido] = admin_logado.get("/api/v1/admin/pedidos").json()["dados"]
    assert pedido["itens"][0]["nome"] == "Bolsa Clássica Chanel"
    assert pedido["cliente"]["nome"] == "Cliente de Teste"


def teste_repetir_o_envio_nao_duplica_o_pedido(cliente_logado, sessao, produto_com_variacoes):
    _adicionar(cliente_logado, sessao, produto_com_variacoes)

    primeira = cliente_logado.post("/api/v1/selecoes")
    repetida = cliente_logado.post("/api/v1/selecoes")

    assert primeira.status_code == repetida.status_code == 200
    assert primeira.json() == repetida.json()
    assert _total_de_pedidos(sessao) == 1


def teste_selecao_diferente_cria_outro_pedido(cliente_logado, sessao, produto_com_variacoes):
    _adicionar(cliente_logado, sessao, produto_com_variacoes)
    assert cliente_logado.post("/api/v1/selecoes").status_code == 200

    outra = criar_produto(
        sessao,
        codigo="TST-OUTRA",
        nome="Carteira Chanel",
        marca=criar_marca(sessao, "Chanel", "chanel"),
        categoria=criar_categoria(sessao, "feminino", "Bolsas", "bolsas"),
        variacoes=[("tamanho", "M"), ("cor", "Preto")],
    )
    sessao.commit()
    _adicionar(cliente_logado, sessao, outra)
    assert cliente_logado.post("/api/v1/selecoes").status_code == 200

    assert _total_de_pedidos(sessao) == 2
    totais = sorted(p.total_itens for p in sessao.scalars(select(Pedido)))
    assert totais == [1, 2]


def teste_pedido_ja_encerrado_nao_barra_um_novo(cliente_logado, sessao, produto_com_variacoes):
    _adicionar(cliente_logado, sessao, produto_com_variacoes)
    assert cliente_logado.post("/api/v1/selecoes").status_code == 200
    sessao.scalar(select(Pedido)).status = "finalizado"
    sessao.commit()

    assert cliente_logado.post("/api/v1/selecoes").status_code == 200

    assert sorted(p.status for p in sessao.scalars(select(Pedido))) == ["em_andamento", "finalizado"]


def teste_envio_vazio(cliente_logado, sessao):
    resposta = cliente_logado.post("/api/v1/selecoes")

    assert resposta.status_code == 400
    assert resposta.json()["erro"]["codigo"] == "CARRINHO_VAZIO"
    assert _total_de_pedidos(sessao) == 0


def teste_rotas_do_historico_antigo_continuam_removidas(cliente_logado, admin_logado):
    # O histórico voltou como /admin/pedidos; as rotas antigas de "seleções" não.
    assert cliente_logado.get("/api/v1/selecoes").status_code == 405
    assert admin_logado.get("/api/v1/admin/selecoes").status_code == 404
    assert admin_logado.get("/api/v1/admin/selecoes/1").status_code == 404
