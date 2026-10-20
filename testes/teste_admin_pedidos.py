"""/admin/pedidos: listagem por status com as peças e os dados do cliente, e a
mudança de status pela equipe."""

from datetime import datetime, timedelta, timezone

from vip_api.modelos.pedido import Pedido, PedidoItem

URL = "/api/v1/admin/pedidos"


def _criar_pedido(sessao, *, status="em_andamento", email="a@teste.local", pecas=1, minutos_atras=0):
    quando = datetime.now(timezone.utc) - timedelta(minutes=minutos_atras)
    pedido = Pedido(
        cliente_nome="Marina",
        cliente_email=email,
        cliente_telefone="41999990000",
        status=status,
        total_itens=pecas,
        criado_em=quando,
        atualizado_em=quando,
    )
    pedido.itens = [
        PedidoItem(
            produto_codigo=f"COD-{ordem}",
            produto_nome=f"Peça {ordem}",
            marca_nome="Chanel",
            categoria_nome="Bolsas",
            colecao_nome="Feminino",
            variacao_tamanho="M" if ordem == 1 else None,
            variacao_cor="Preto" if ordem == 1 else None,
            ordem=ordem,
        )
        for ordem in range(1, pecas + 1)
    ]
    sessao.add(pedido)
    sessao.commit()
    return pedido


def teste_lista_do_mais_novo_com_pecas_e_cliente(admin_logado, sessao):
    _criar_pedido(sessao, email="velho@teste.local", minutos_atras=60)
    _criar_pedido(sessao, email="novo@teste.local", pecas=2, minutos_atras=5)

    corpo = admin_logado.get(URL).json()

    assert [p["cliente"]["email"] for p in corpo["dados"]] == ["novo@teste.local", "velho@teste.local"]
    pedido = corpo["dados"][0]
    assert pedido["status"] == "em_andamento"
    assert pedido["totalItens"] == 2
    assert pedido["cliente"] == {
        "id": None,
        "nome": "Marina",
        "email": "novo@teste.local",
        "telefone": "41999990000",
    }
    assert [i["codigo"] for i in pedido["itens"]] == ["COD-1", "COD-2"]
    assert pedido["itens"][0] == {
        "produtoId": None,
        "codigo": "COD-1",
        "nome": "Peça 1",
        "marca": "Chanel",
        "categoria": "Bolsas",
        "colecao": "Feminino",
        "imagemUrl": None,
        "tamanho": "M",
        "cor": "Preto",
    }
    assert {"criadoEm", "atualizadoEm"} <= set(pedido)


def teste_contagens_sao_do_banco_inteiro_e_o_filtro_so_da_a_lista(admin_logado, sessao):
    _criar_pedido(sessao, status="em_andamento")
    _criar_pedido(sessao, status="em_andamento")
    _criar_pedido(sessao, status="finalizado")
    _criar_pedido(sessao, status="nao_finalizado")

    todos = admin_logado.get(URL).json()
    so_finalizados = admin_logado.get(URL, params={"status": "finalizado"}).json()

    contagens = {"emAndamento": 2, "finalizado": 1, "naoFinalizado": 1, "total": 4}
    assert todos["contagens"] == contagens
    assert todos["paginacao"]["total"] == 4
    assert so_finalizados["contagens"] == contagens
    assert so_finalizados["paginacao"]["total"] == 1
    assert [p["status"] for p in so_finalizados["dados"]] == ["finalizado"]


def teste_paginacao_numerada(admin_logado, sessao):
    for minutos in range(5):
        _criar_pedido(sessao, email=f"p{minutos}@teste.local", minutos_atras=minutos)

    segunda = admin_logado.get(URL, params={"pagina": 2, "porPagina": 2}).json()

    assert [p["cliente"]["email"] for p in segunda["dados"]] == ["p2@teste.local", "p3@teste.local"]
    assert segunda["paginacao"] == {"total": 5, "porPagina": 2, "pagina": 2}


def teste_lista_vazia(admin_logado):
    corpo = admin_logado.get(URL).json()

    assert corpo["dados"] == []
    assert corpo["contagens"] == {"emAndamento": 0, "finalizado": 0, "naoFinalizado": 0, "total": 0}


def teste_status_desconhecido_na_busca_e_recusado(admin_logado):
    resposta = admin_logado.get(URL, params={"status": "cancelado"})

    assert resposta.status_code == 400
    assert resposta.json()["erro"]["codigo"] == "DADOS_INVALIDOS"


def teste_listar_nao_faz_uma_consulta_por_pedido(admin_logado, sessao, contar_consultas):
    for minutos in range(6):
        _criar_pedido(sessao, pecas=3, minutos_atras=minutos)

    with contar_consultas() as consultas:
        resposta = admin_logado.get(URL)

    assert len(resposta.json()["dados"]) == 6
    # contagens, pedidos da página e as peças de todos eles.
    assert len(consultas) == 3, consultas


def teste_muda_o_status_e_a_data_da_mudanca(admin_logado, sessao):
    pedido = _criar_pedido(sessao, minutos_atras=30)

    resposta = admin_logado.patch(f"{URL}/{pedido.id}", json={"status": "finalizado"})

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["status"] == "finalizado"
    assert corpo["atualizadoEm"] > corpo["criadoEm"]
    assert [i["codigo"] for i in corpo["itens"]] == ["COD-1"]
    sessao.refresh(pedido)
    assert pedido.status == "finalizado"


def teste_qualquer_status_vale_para_qualquer_outro(admin_logado, sessao):
    pedido = _criar_pedido(sessao, status="nao_finalizado")

    for novo in ("em_andamento", "finalizado", "nao_finalizado"):
        resposta = admin_logado.patch(f"{URL}/{pedido.id}", json={"status": novo})
        assert resposta.status_code == 200
        assert resposta.json()["status"] == novo


def teste_repetir_o_mesmo_status_nao_mexe_na_data(admin_logado, sessao):
    pedido = _criar_pedido(sessao, minutos_atras=30)
    antes = pedido.atualizado_em

    resposta = admin_logado.patch(f"{URL}/{pedido.id}", json={"status": "em_andamento"})

    assert resposta.status_code == 200
    sessao.refresh(pedido)
    assert pedido.atualizado_em == antes


def teste_pedido_inexistente_da_404(admin_logado):
    resposta = admin_logado.patch(f"{URL}/999999", json={"status": "finalizado"})

    assert resposta.status_code == 404
    assert resposta.json()["erro"]["codigo"] == "PEDIDO_NAO_ENCONTRADO"


def teste_status_invalido_no_corpo_e_recusado(admin_logado, sessao):
    pedido = _criar_pedido(sessao)

    resposta = admin_logado.patch(f"{URL}/{pedido.id}", json={"status": "cancelado"})

    assert resposta.status_code == 400
    sessao.refresh(pedido)
    assert pedido.status == "em_andamento"


def teste_so_o_painel_ve_pedidos(sem_sessao, cliente_logado):
    assert sem_sessao.get(URL).status_code == 401
    assert cliente_logado.get(URL).status_code == 403
    assert cliente_logado.patch(f"{URL}/1", json={"status": "finalizado"}).status_code == 403
