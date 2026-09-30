"""CRUD de categorias no painel (tarefa 57; revisto na migração 0015).

Desde a 0015 a categoria não pertence a coleção: o slug é único na tabela toda, e Feminino e
Masculino são o público do produto. Ver o docstring de servicos/admin_categorias.py.
"""

import pytest
from sqlalchemy import func, select

from testes.fabrica import criar_categoria, criar_marca, criar_produto
from vip_api.modelos.catalogo import Categoria, Produto

ROTA = "/api/v1/admin/categorias"


@pytest.fixture
def categoria_com_produtos(sessao):
    marca = criar_marca(sessao, "Chanel", "chanel")
    categoria = criar_categoria(sessao, "feminino", "Bolsas", "bolsas")
    for indice in range(4):
        criar_produto(
            sessao, f"CHN-95{indice:02d}", f"Bolsa {indice}", marca, categoria, com_imagem=False
        )
    sessao.commit()
    return categoria


def teste_criar_gera_slug_a_partir_do_nome(admin_logado):
    resposta = admin_logado.post(ROTA, json={"nome": "Coleção de verão"})

    assert resposta.status_code == 201
    assert resposta.json()["slug"] == "colecao-de-verao"
    assert resposta.json()["ativa"] is True
    assert "colecaoId" not in resposta.json()


def teste_slug_repetido_responde_409(admin_logado):
    admin_logado.post(ROTA, json={"nome": "Bolsas"})

    resposta = admin_logado.post(ROTA, json={"nome": "Bolsas", "slug": "bolsas"})

    assert resposta.status_code == 409
    assert resposta.json()["erro"]["codigo"] == "SLUG_EM_USO"


def teste_criar_sem_slug_desambigua(admin_logado):
    primeira = admin_logado.post(ROTA, json={"nome": "Bolsas"}).json()
    segunda = admin_logado.post(ROTA, json={"nome": "Bolsas"}).json()

    assert primeira["slug"] == "bolsas"
    assert segunda["slug"] == "bolsas-2"


def teste_criar_sem_nome_responde_400(admin_logado):
    resposta = admin_logado.post(ROTA, json={"nome": ""})

    assert resposta.status_code == 400
    assert "nome" in resposta.json()["erro"]["campos"]


def teste_editar_o_nome_nao_muda_o_slug(admin_logado, categoria_com_produtos):
    resposta = admin_logado.patch(
        f"{ROTA}/{categoria_com_produtos.id}", json={"nome": "Bolsas e Carteiras"}
    )

    assert resposta.json()["nome"] == "Bolsas e Carteiras"
    assert resposta.json()["slug"] == "bolsas"


def teste_editar_slug_para_um_que_ja_existe_responde_409(admin_logado, sessao):
    criar_categoria(sessao, "feminino", "Sapatos", "sapatos")
    bolsas = criar_categoria(sessao, "feminino", "Bolsas", "bolsas")
    sessao.commit()

    resposta = admin_logado.patch(f"{ROTA}/{bolsas.id}", json={"slug": "sapatos"})

    assert resposta.status_code == 409
    assert resposta.json()["erro"]["codigo"] == "SLUG_EM_USO"


def teste_excluir_categoria_com_produtos_responde_409_com_a_contagem(
    admin_logado, sessao, categoria_com_produtos
):
    real = sessao.scalar(
        select(func.count())
        .select_from(Produto)
        .where(Produto.categoria_id == categoria_com_produtos.id)
    )

    resposta = admin_logado.delete(f"{ROTA}/{categoria_com_produtos.id}")

    assert resposta.status_code == 409
    erro = resposta.json()["erro"]
    assert erro["codigo"] == "CATEGORIA_COM_PRODUTOS"
    assert f"{real} produtos usam esta categoria" in erro["mensagem"]
    assert erro["detalhes"]["totalProdutos"] == real
    sessao.expire_all()
    assert sessao.get(Categoria, categoria_com_produtos.id) is not None


def teste_excluir_categoria_sem_produtos_funciona(admin_logado, sessao):
    categoria = criar_categoria(sessao, "masculino", "Cintos", "cintos")
    sessao.commit()

    assert admin_logado.delete(f"{ROTA}/{categoria.id}").status_code == 200
    sessao.expire_all()
    assert sessao.get(Categoria, categoria.id) is None


def teste_listagem_conta_produtos_e_traz_todas_as_categorias(
    admin_logado, sessao, categoria_com_produtos
):
    criar_categoria(sessao, "masculino", "Sapatos", "sapatos")
    sessao.commit()

    todas = admin_logado.get(ROTA).json()

    assert {c["slug"] for c in todas} == {"bolsas", "sapatos"}
    assert [c for c in todas if c["slug"] == "bolsas"][0]["totalProdutos"] == 4
    assert [c for c in todas if c["slug"] == "sapatos"][0]["totalProdutos"] == 0


def teste_categoria_inexistente_responde_404(admin_logado):
    assert admin_logado.patch(f"{ROTA}/99999", json={"nome": "X"}).status_code == 404
    assert admin_logado.delete(f"{ROTA}/99999").status_code == 404
