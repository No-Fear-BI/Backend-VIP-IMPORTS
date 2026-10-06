"""Consultas do painel: resumo e clientes (tarefa 60).

Cada número é conferido contra uma contagem feita direto no banco, na mesma
transação — comparar a resposta com outra soma escrita à mão no teste provaria
só que as duas contas erram igual.
"""

import pytest
from sqlalchemy import func, select

from testes.fabrica import criar_marca
from vip_api.modelos.catalogo import Produto
from vip_api.modelos.cliente import Cliente

RESUMO = "/api/v1/admin/resumo"
CLIENTES = "/api/v1/admin/clientes"


@pytest.fixture
def loja(sessao, catalogo):
    """Catálogo de 66 produtos (60 visíveis, 6 ocultos) mais três clientes com
    cadastrados."""
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
    assert "selecoesNoMes" not in corpo

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



def teste_resumo_cabe_no_orcamento_de_consultas(admin_logado, sessao, loja, contar_consultas):
    """Quatro consultas é o teto da rota; esta implementação usa três."""
    with contar_consultas() as consultas:
        admin_logado.get(RESUMO)

    assert len(consultas) <= 4, "\n".join(consultas)


# ======================================================================
# Seleções
# ======================================================================








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


def teste_clientes_sem_contagem_de_pedidos(admin_logado, loja):
    resposta = admin_logado.get(CLIENTES)
    assert resposta.status_code == 200
    assert all("totalSelecoes" not in c for c in resposta.json()["dados"])
