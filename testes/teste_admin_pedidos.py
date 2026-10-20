"""Aba Pedidos do painel: lista com dados do cliente, filtro de pagamento e confirmação."""

from vip_api.modelos.pedido import Pedido

PEDIDOS = "/api/v1/admin/pedidos"


def _pedido(sessao, nome, email, pago=False):
    p = Pedido(
        cliente_nome=nome,
        cliente_email=email,
        cliente_telefone="41999990000",
        itens=[{"codigo": "X030", "nome": "Jaqueta", "marca": "Chanel", "variacao": "M / Preto"}],
        pago=pago,
    )
    sessao.add(p)
    sessao.commit()
    return p


def teste_lista_traz_dados_do_cliente_e_situacao(admin_logado, sessao):
    _pedido(sessao, "Ana", "ana@teste.local", pago=True)
    _pedido(sessao, "Bia", "bia@teste.local")

    corpo = admin_logado.get(PEDIDOS).json()
    assert corpo["paginacao"]["total"] == 2
    ana = next(p for p in corpo["dados"] if p["clienteEmail"] == "ana@teste.local")
    assert ana["clienteNome"] == "Ana" and ana["clienteTelefone"] == "41999990000"
    assert ana["pago"] is True
    assert ana["itens"][0]["codigo"] == "X030"


def teste_filtra_por_situacao_e_busca(admin_logado, sessao):
    _pedido(sessao, "Ana", "ana@teste.local", pago=True)
    _pedido(sessao, "Bia", "bia@teste.local")

    assert [p["clienteNome"] for p in admin_logado.get(PEDIDOS, params={"situacao": "pendente"}).json()["dados"]] == ["Bia"]
    assert [p["clienteNome"] for p in admin_logado.get(PEDIDOS, params={"busca": "ana@"}).json()["dados"]] == ["Ana"]


def teste_marcar_pago_e_desfazer(admin_logado, sessao):
    pedido = _pedido(sessao, "Ana", "ana@teste.local")

    pago = admin_logado.patch(f"{PEDIDOS}/{pedido.id}", json={"pago": True}).json()
    assert pago["pago"] is True and pago["pagoEm"] is not None

    pendente = admin_logado.patch(f"{PEDIDOS}/{pedido.id}", json={"pago": False}).json()
    assert pendente["pago"] is False and pendente["pagoEm"] is None


def teste_pedido_inexistente(admin_logado):
    assert admin_logado.patch(f"{PEDIDOS}/999999", json={"pago": True}).status_code == 404

