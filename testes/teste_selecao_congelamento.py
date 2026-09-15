"""A seleção enviada é dado CONGELADO.

Herdado do passo `congelamento` do antigo roteiro de verificação da Fatia 3. O
painel de atendimento precisa mostrar o que o cliente VIU, não o que o produto
é hoje: se a atendente abre uma seleção de três semanas atrás e cita um nome
que mudou nesse meio-tempo, a conversa descarrila.
"""

from sqlalchemy import select, update

from vip_api.modelos.catalogo import Produto, ProdutoVariacao

NOME_NOVO = "PRODUTO RENOMEADO DEPOIS DO ENVIO"


def _variacoes(sessao, produto):
    return (
        sessao.scalar(
            select(ProdutoVariacao.id).where(
                ProdutoVariacao.produto_id == produto.id, ProdutoVariacao.tipo == "tamanho"
            )
        ),
        sessao.scalar(
            select(ProdutoVariacao.id).where(
                ProdutoVariacao.produto_id == produto.id, ProdutoVariacao.tipo == "cor"
            )
        ),
    )


def _enviar_selecao(http, sessao, produto):
    tamanho, cor = _variacoes(sessao, produto)
    http.post(
        "/api/v1/carrinho",
        json={"produtoId": produto.id, "variacaoTamanhoId": tamanho, "variacaoCorId": cor},
    )
    resposta = http.post("/api/v1/selecoes")
    # 201: a seleção enviada é registro novo, ao contrário das outras rotas de
    # escrita do contrato, que respondem 200.
    assert resposta.status_code == 201
    return resposta.json()


def teste_selecao_congela_nome_e_variacoes(cliente_logado, sessao, produto_com_variacoes):
    enviada = _enviar_selecao(cliente_logado, sessao, produto_com_variacoes)
    nome_original = produto_com_variacoes.nome

    sessao.execute(
        update(Produto).where(Produto.id == produto_com_variacoes.id).values(nome=NOME_NOVO)
    )
    sessao.commit()

    historico = cliente_logado.get("/api/v1/selecoes")
    assert historico.status_code == 200
    (selecao,) = [s for s in historico.json()["dados"] if s["id"] == enviada["id"]]
    (item,) = selecao["itens"]

    assert item["nome"] == nome_original
    assert item["nome"] != NOME_NOVO
    # O par congelado também: o rótulo continua composto dos dois valores.
    assert item["variacao"] == "M / Preto"


def teste_mensagem_do_whatsapp_traz_o_par(cliente_logado, sessao, produto_com_variacoes):
    enviada = _enviar_selecao(cliente_logado, sessao, produto_com_variacoes)

    assert "(Chanel, M / Preto)" in enviada["mensagemWhatsapp"]
    assert enviada["linkWhatsapp"].startswith("https://wa.me/")


def teste_produto_apagado_nao_leva_o_historico_junto(
    cliente_logado, sessao, produto_com_variacoes
):
    """FK nulável e SEM cascata: apagar o produto deixa a linha da seleção
    intacta, só sem o link."""
    enviada = _enviar_selecao(cliente_logado, sessao, produto_com_variacoes)

    sessao.execute(
        Produto.__table__.delete().where(Produto.id == produto_com_variacoes.id)
    )
    sessao.commit()

    historico = cliente_logado.get("/api/v1/selecoes")
    (selecao,) = [s for s in historico.json()["dados"] if s["id"] == enviada["id"]]

    assert selecao["totalItens"] == 1
    assert selecao["itens"][0]["codigo"] == "TST-PAR"


def teste_carrinho_nao_e_esvaziado_pelo_envio(cliente_logado, sessao, produto_com_variacoes):
    """Se a pessoa abrir o link e fechar o WhatsApp sem mandar nada, esvaziar
    teria destruído a seleção dela."""
    _enviar_selecao(cliente_logado, sessao, produto_com_variacoes)

    carrinho = cliente_logado.get("/api/v1/carrinho")

    assert len(carrinho.json()) == 1
