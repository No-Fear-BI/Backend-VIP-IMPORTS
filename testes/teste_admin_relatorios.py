"""Consultas do painel: resumo, seleções recebidas e clientes (tarefa 60).

Cada número é conferido contra uma contagem feita direto no banco, na mesma
transação — comparar a resposta com outra soma escrita à mão no teste provaria
só que as duas contas erram igual.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, func, select

from testes.fabrica import criar_categoria, criar_marca, criar_produto, criar_selecao
from vip_api.modelos.catalogo import Marca, Produto
from vip_api.modelos.cliente import Cliente
from vip_api.modelos.selecao import Selecao, SelecaoItem

RESUMO = "/api/v1/admin/resumo"
SELECOES = "/api/v1/admin/selecoes"
CLIENTES = "/api/v1/admin/clientes"


@pytest.fixture
def loja(sessao, catalogo):
    """Catálogo de 66 produtos (60 visíveis, 6 ocultos) mais três clientes com
    seleções enviadas."""
    clientes = []
    for indice in range(3):
        pessoa = Cliente(
            email=f"cliente{indice}@teste.local",
            nome=f"Cliente {indice}",
            telefone=f"4199999000{indice}",
        )
        sessao.add(pessoa)
        clientes.append(pessoa)
    sessao.flush()

    # Quantidades diferentes de propósito: a contagem por cliente tem que
    # distinguir quem manda muito de quem mandou uma vez.
    for numero, pessoa in enumerate(clientes, start=1):
        for _ in range(numero):
            criar_selecao(sessao, pessoa, catalogo.visiveis[:3])
    sessao.commit()
    return clientes


# ======================================================================
# Resumo
# ======================================================================


def teste_resumo_bate_com_o_banco(admin_logado, sessao, loja):
    corpo = admin_logado.get(RESUMO).json()

    assert corpo["totalProdutos"] == sessao.scalar(
        select(func.count()).select_from(Produto)
    )
    assert corpo["produtosEsgotados"] == sessao.scalar(
        select(func.count()).select_from(Produto).where(Produto.status == "esgotado")
    )
    assert corpo["produtosOcultos"] == sessao.scalar(
        select(func.count()).select_from(Produto).where(Produto.status == "oculto")
    )
    assert corpo["totalClientes"] == sessao.scalar(
        select(func.count()).select_from(Cliente)
    )
    assert corpo["selecoesNoMes"] == sessao.scalar(
        select(func.count()).select_from(Selecao)
    )

    por_marca_no_banco = {
        marca_id: total
        for marca_id, total in sessao.execute(
            select(Produto.marca_id, func.count()).group_by(Produto.marca_id)
        )
    }
    por_marca = {linha["marcaId"]: linha["total"] for linha in corpo["porMarca"]}
    for marca_id, total in por_marca_no_banco.items():
        assert por_marca[marca_id] == total


def teste_resumo_traz_marca_sem_produto_com_zero(admin_logado, sessao, loja):
    """Marca com zero é justamente o que interessa a quem limpa cadastro."""
    criar_marca(sessao, "Marca Vazia", "marca-vazia")
    sessao.commit()

    corpo = admin_logado.get(RESUMO).json()

    vazia = [m for m in corpo["porMarca"] if m["slug"] == "marca-vazia"]
    assert vazia and vazia[0]["total"] == 0


def teste_selecoes_no_mes_ignora_o_mes_passado(admin_logado, sessao, loja):
    antiga = sessao.scalars(select(Selecao)).first()
    antes = admin_logado.get(RESUMO).json()["selecoesNoMes"]

    # Joga uma seleção para o mês anterior.
    antiga.criado_em = datetime.now(timezone.utc).replace(day=1) - timedelta(days=2)
    sessao.commit()

    assert admin_logado.get(RESUMO).json()["selecoesNoMes"] == antes - 1


def teste_resumo_cabe_no_orcamento_de_consultas(admin_logado, sessao, loja, contar_consultas):
    """Quatro consultas é o teto da rota; esta implementação usa três."""
    with contar_consultas() as consultas:
        admin_logado.get(RESUMO)

    assert len(consultas) <= 4, "\n".join(consultas)


# ======================================================================
# Seleções
# ======================================================================


def teste_listagem_de_selecoes_pagina_e_ordena(admin_logado, sessao, loja):
    total = sessao.scalar(select(func.count()).select_from(Selecao))

    primeira = admin_logado.get(SELECOES, params={"porPagina": 4, "pagina": 1}).json()
    segunda = admin_logado.get(SELECOES, params={"porPagina": 4, "pagina": 2}).json()

    assert primeira["paginacao"] == {"total": total, "porPagina": 4, "pagina": 1}
    assert len(primeira["dados"]) == 4
    assert len(segunda["dados"]) == total - 4
    # Mais recentes primeiro.
    ids = [s["id"] for s in primeira["dados"] + segunda["dados"]]
    assert ids == sorted(ids, reverse=True)
    # Cada seleção traz o e-mail de quem enviou e os itens congelados.
    assert primeira["dados"][0]["cliente"]["email"].endswith("@teste.local")
    assert len(primeira["dados"][0]["itens"]) == 3


def teste_listagem_de_selecoes_sem_n_mais_um(admin_logado, sessao, loja, contar_consultas):
    """Os itens de TODAS as seleções da página saem numa consulta só."""
    with contar_consultas() as consultas:
        admin_logado.get(SELECOES, params={"porPagina": 6})

    assert len(consultas) <= 3, "\n".join(consultas)


def teste_detalhe_da_selecao(admin_logado, sessao, loja):
    selecao = sessao.scalars(select(Selecao)).first()

    corpo = admin_logado.get(f"{SELECOES}/{selecao.id}").json()

    assert corpo["id"] == selecao.id
    assert corpo["cliente"]["email"] == selecao.cliente_email
    assert corpo["cliente"]["telefone"] == selecao.cliente_telefone
    assert len(corpo["itens"]) == selecao.total_itens


def teste_selecao_de_produto_excluido_continua_inteira(
    admin_logado, sessao, loja, catalogo
):
    """O congelamento é o que sustenta isto: a linha da seleção não depende de
    o produto existir."""
    selecao = sessao.scalars(select(Selecao)).first()
    excluido = catalogo.visiveis[0]
    antes = admin_logado.get(f"{SELECOES}/{selecao.id}").json()
    (item_antes,) = [i for i in antes["itens"] if i["produtoId"] == excluido.id]

    assert admin_logado.delete(f"/api/v1/admin/produtos/{excluido.id}").status_code == 200

    depois = admin_logado.get(f"{SELECOES}/{selecao.id}").json()

    assert len(depois["itens"]) == len(antes["itens"])
    (item_depois,) = [i for i in depois["itens"] if i["codigo"] == item_antes["codigo"]]
    assert item_depois["produtoId"] is None
    assert item_depois["nome"] == item_antes["nome"]
    assert item_depois["marca"] == item_antes["marca"]
    assert item_depois["imagemUrl"] == item_antes["imagemUrl"]


def teste_selecao_inexistente_responde_404(admin_logado):
    assert admin_logado.get(f"{SELECOES}/999999").status_code == 404


# ======================================================================
# Clientes
# ======================================================================


def teste_clientes_trazem_a_contagem_de_selecoes(admin_logado, sessao, loja):
    corpo = admin_logado.get(CLIENTES, params={"porPagina": 100}).json()

    por_email = {c["email"]: c["totalSelecoes"] for c in corpo["dados"]}
    for pessoa in loja:
        real = sessao.scalar(
            select(func.count()).select_from(Selecao).where(Selecao.cliente_id == pessoa.id)
        )
        assert por_email[pessoa.email] == real
    assert sorted(por_email[p.email] for p in loja) == [1, 2, 3]


def teste_clientes_sem_n_mais_um(admin_logado, sessao, loja, contar_consultas):
    with contar_consultas() as consultas:
        admin_logado.get(CLIENTES, params={"porPagina": 100})

    assert len(consultas) <= 2, "\n".join(consultas)


def teste_busca_por_email(admin_logado, sessao, loja):
    alvo = loja[1]

    corpo = admin_logado.get(CLIENTES, params={"busca": alvo.email.split("@")[0]}).json()

    assert [c["email"] for c in corpo["dados"]] == [alvo.email]
    assert corpo["paginacao"]["total"] == 1


def teste_busca_ignora_caixa(admin_logado, loja):
    corpo = admin_logado.get(CLIENTES, params={"busca": "CLIENTE1@TESTE.LOCAL"}).json()

    assert corpo["paginacao"]["total"] == 1


def teste_clientes_pagina(admin_logado, sessao, loja):
    total = sessao.scalar(select(func.count()).select_from(Cliente))

    primeira = admin_logado.get(CLIENTES, params={"porPagina": 2, "pagina": 1}).json()
    segunda = admin_logado.get(CLIENTES, params={"porPagina": 2, "pagina": 2}).json()

    assert primeira["paginacao"]["total"] == total
    assert len(primeira["dados"]) == 2
    assert len(segunda["dados"]) == min(2, total - 2)
    ids = [c["id"] for c in primeira["dados"] + segunda["dados"]]
    assert len(ids) == len(set(ids))


def teste_telefone_aparece_no_painel(admin_logado, loja):
    """No painel o telefone aparece — é com ele que o atendimento responde a
    seleção. Nenhuma rota pública devolve telefone de terceiro."""
    corpo = admin_logado.get(CLIENTES, params={"porPagina": 100}).json()

    (cliente,) = [c for c in corpo["dados"] if c["email"] == loja[0].email]
    assert cliente["telefone"] == loja[0].telefone
