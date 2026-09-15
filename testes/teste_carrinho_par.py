"""O item do carrinho guarda um PAR de variações — e o banco segura o par.

Herdado dos passos `restricao` e `unicidade` do antigo roteiro de verificação
da Fatia 3. Duas camadas:

- No BANCO: cor na coluna de tamanho (ou o contrário) é recusada pela FK
  composta (id, tipo) e pela CHECK do tipo, mesmo sem passar pela API.
- Na API: a mesma inversão volta 400 VARIACAO_INVALIDA no campo certo, e o
  UNIQUE NULLS NOT DISTINCT faz "mesmo produto, mesmo par" ser um item só —
  inclusive o par vazio e a troca de par que colide com outro item.
"""

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from vip_api.modelos.catalogo import ProdutoVariacao
from vip_api.servicos.carrinho import obter_ou_criar_carrinho

ROTA = "/api/v1/carrinho"


def _variacoes(sessao, produto):
    def de_tipo(tipo):
        return sessao.scalar(
            select(ProdutoVariacao.id).where(
                ProdutoVariacao.produto_id == produto.id, ProdutoVariacao.tipo == tipo
            )
        )

    return de_tipo("tamanho"), de_tipo("cor")


def _inserir(sessao, colunas: dict) -> None:
    nomes = ", ".join(colunas)
    marcadores = ", ".join(f":{nome}" for nome in colunas)
    # SAVEPOINT próprio: a recusa do banco aborta só este trecho, não a
    # transação do teste inteiro.
    with sessao.begin_nested():
        sessao.execute(
            text(f"INSERT INTO carrinho_itens ({nomes}) VALUES ({marcadores})"), colunas
        )


@pytest.mark.parametrize(
    "rotulo,montar",
    [
        ("cor na coluna de tamanho", lambda t, c: {"variacao_tamanho_id": c}),
        (
            "cor na coluna de tamanho, declarando o tipo 'cor'",
            lambda t, c: {"variacao_tamanho_id": c, "variacao_tamanho_tipo": "cor"},
        ),
        ("tamanho na coluna de cor", lambda t, c: {"variacao_cor_id": t}),
    ],
)
def teste_banco_recusa_variacao_na_coluna_errada(
    sessao, cliente, produto_com_variacoes, rotulo, montar
):
    tamanho, cor = _variacoes(sessao, produto_com_variacoes)
    carrinho = obter_ou_criar_carrinho(sessao, cliente.id)

    with pytest.raises(IntegrityError):
        _inserir(
            sessao,
            {"carrinho_id": carrinho.id, "produto_id": produto_com_variacoes.id, **montar(tamanho, cor)},
        )


def teste_banco_aceita_o_par_nas_colunas_certas(sessao, cliente, produto_com_variacoes):
    tamanho, cor = _variacoes(sessao, produto_com_variacoes)
    carrinho = obter_ou_criar_carrinho(sessao, cliente.id)

    _inserir(
        sessao,
        {
            "carrinho_id": carrinho.id,
            "produto_id": produto_com_variacoes.id,
            "variacao_tamanho_id": tamanho,
            "variacao_cor_id": cor,
        },
    )


def teste_api_recusa_o_par_invertido_no_campo_certo(cliente_logado, sessao, produto_com_variacoes):
    """O serviço recusa antes do banco: sem isso, a FK composta viraria 500."""
    tamanho, cor = _variacoes(sessao, produto_com_variacoes)

    resposta = cliente_logado.post(
        ROTA,
        json={
            "produtoId": produto_com_variacoes.id,
            "variacaoTamanhoId": cor,
            "variacaoCorId": tamanho,
        },
    )

    assert resposta.status_code == 400
    erro = resposta.json()["erro"]
    assert erro["codigo"] == "VARIACAO_INVALIDA"
    assert "variacaoTamanhoId" in erro["campos"]


def teste_mesmo_par_e_um_item_so_inclusive_o_vazio(cliente_logado, sessao, produto_com_variacoes):
    tamanho, cor = _variacoes(sessao, produto_com_variacoes)
    produto = produto_com_variacoes.id
    envios = [
        {"variacaoTamanhoId": tamanho, "variacaoCorId": cor},
        {"variacaoTamanhoId": tamanho, "variacaoCorId": cor},
        {"variacaoTamanhoId": tamanho},
        {"variacaoCorId": cor},
        {},
        {},
    ]
    for extra in envios:
        assert cliente_logado.post(ROTA, json={"produtoId": produto, **extra}).status_code == 200

    itens = cliente_logado.get(ROTA).json()
    pares = sorted(
        (
            ((i["variacaoTamanho"] or {}).get("id") or 0),
            ((i["variacaoCor"] or {}).get("id") or 0),
        )
        for i in itens
    )
    # Seis envios, quatro pares distintos: completo, só tamanho, só cor, vazio.
    assert pares == sorted([(tamanho, cor), (tamanho, 0), (0, cor), (0, 0)])


def teste_trocar_o_par_para_um_que_ja_existe_junta_os_dois(
    cliente_logado, sessao, produto_com_variacoes
):
    tamanho, cor = _variacoes(sessao, produto_com_variacoes)
    produto = produto_com_variacoes.id
    cliente_logado.post(
        ROTA, json={"produtoId": produto, "variacaoTamanhoId": tamanho, "variacaoCorId": cor}
    )
    cliente_logado.post(ROTA, json={"produtoId": produto, "variacaoCorId": cor})
    (so_cor,) = [i for i in cliente_logado.get(ROTA).json() if i["variacaoTamanho"] is None]

    resposta = cliente_logado.patch(
        f"{ROTA}/{so_cor['itemId']}", json={"variacaoTamanhoId": tamanho, "variacaoCorId": cor}
    )

    assert resposta.status_code == 200
    (item,) = cliente_logado.get(ROTA).json()
    assert (item["variacaoTamanho"]["id"], item["variacaoCor"]["id"]) == (tamanho, cor)
