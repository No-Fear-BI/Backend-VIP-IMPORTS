"""CRUD de categorias no painel (tarefa 57).

O slug da categoria é único POR COLEÇÃO: "bolsas" existe em Feminino e em
Masculino e são categorias diferentes. E trocar a coleção de uma categoria que
já tem produtos é recusado — ver o docstring de servicos/admin_categorias.py.
"""

import pytest
from sqlalchemy import func, select

from testes.fabrica import criar_categoria, criar_marca, criar_produto
from vip_api.modelos.catalogo import Categoria, Colecao, Produto

ROTA = "/api/v1/admin/categorias"


@pytest.fixture
def colecoes(sessao) -> dict[str, int]:
    """As duas coleções fixas da migração 0002. Não existe CRUD para elas."""
    return {
        colecao.slug: colecao.id for colecao in sessao.scalars(select(Colecao))
    }


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


def teste_criar_gera_slug_e_aceita_o_mesmo_nome_nas_duas_colecoes(admin_logado, colecoes):
    feminino = admin_logado.post(
        ROTA, json={"nome": "Bolsas", "colecaoId": colecoes["feminino"]}
    )
    masculino = admin_logado.post(
        ROTA, json={"nome": "Bolsas", "colecaoId": colecoes["masculino"]}
    )

    assert feminino.status_code == 201
    assert masculino.status_code == 201
    assert feminino.json()["slug"] == masculino.json()["slug"] == "bolsas"
    assert feminino.json()["colecaoSlug"] == "feminino"
    assert masculino.json()["colecaoSlug"] == "masculino"
    assert feminino.json()["id"] != masculino.json()["id"]


def teste_slug_repetido_na_mesma_colecao_responde_409(admin_logado, colecoes):
    admin_logado.post(ROTA, json={"nome": "Bolsas", "colecaoId": colecoes["feminino"]})

    resposta = admin_logado.post(
        ROTA, json={"nome": "Bolsas", "colecaoId": colecoes["feminino"], "slug": "bolsas"}
    )

    assert resposta.status_code == 409
    assert resposta.json()["erro"]["codigo"] == "SLUG_EM_USO"
    assert "feminino" in resposta.json()["erro"]["mensagem"]


def teste_criar_sem_slug_desambigua_dentro_da_colecao(admin_logado, colecoes):
    primeira = admin_logado.post(
        ROTA, json={"nome": "Bolsas", "colecaoId": colecoes["feminino"]}
    ).json()
    segunda = admin_logado.post(
        ROTA, json={"nome": "Bolsas", "colecaoId": colecoes["feminino"]}
    ).json()

    assert primeira["slug"] == "bolsas"
    assert segunda["slug"] == "bolsas-2"


def teste_colecao_inexistente_responde_400(admin_logado):
    resposta = admin_logado.post(ROTA, json={"nome": "Bolsas", "colecaoId": 999})

    assert resposta.status_code == 400
    assert "colecaoId" in resposta.json()["erro"]["campos"]


def teste_editar_o_nome_nao_muda_o_slug(admin_logado, categoria_com_produtos):
    resposta = admin_logado.patch(
        f"{ROTA}/{categoria_com_produtos.id}", json={"nome": "Bolsas e Carteiras"}
    )

    assert resposta.json()["nome"] == "Bolsas e Carteiras"
    assert resposta.json()["slug"] == "bolsas"


def teste_trocar_a_colecao_com_produtos_responde_409(
    admin_logado, sessao, categoria_com_produtos, colecoes
):
    """A FK composta amarra produto e categoria à mesma coleção, e não é
    adiável: mover as duas pontas juntas não cabe numa transação. O caminho é
    criar a categoria do outro lado e mover os produtos pelo lote."""
    real = sessao.scalar(
        select(func.count())
        .select_from(Produto)
        .where(Produto.categoria_id == categoria_com_produtos.id)
    )

    resposta = admin_logado.patch(
        f"{ROTA}/{categoria_com_produtos.id}", json={"colecaoId": colecoes["masculino"]}
    )

    assert resposta.status_code == 409
    erro = resposta.json()["erro"]
    assert erro["codigo"] == "CATEGORIA_COM_PRODUTOS"
    assert f"{real} produtos usam esta categoria" in erro["mensagem"]
    assert "PATCH /admin/produtos/lote" in erro["mensagem"]
    assert erro["detalhes"]["totalProdutos"] == real

    sessao.expire_all()
    assert sessao.get(Categoria, categoria_com_produtos.id).colecao_id == colecoes["feminino"]


def teste_trocar_a_colecao_sem_produtos_funciona(admin_logado, sessao, colecoes):
    categoria = criar_categoria(sessao, "feminino", "Chapéus", "chapeus")
    sessao.commit()

    resposta = admin_logado.patch(
        f"{ROTA}/{categoria.id}", json={"colecaoId": colecoes["masculino"]}
    )

    assert resposta.status_code == 200
    assert resposta.json()["colecaoSlug"] == "masculino"
    sessao.expire_all()
    assert sessao.get(Categoria, categoria.id).colecao_id == colecoes["masculino"]


def teste_trocar_a_colecao_para_onde_o_slug_ja_existe_responde_409(
    admin_logado, sessao, colecoes
):
    criar_categoria(sessao, "masculino", "Bolsas", "bolsas")
    de_mudanca = criar_categoria(sessao, "feminino", "Bolsas", "bolsas")
    sessao.commit()

    resposta = admin_logado.patch(
        f"{ROTA}/{de_mudanca.id}", json={"colecaoId": colecoes["masculino"]}
    )

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
    sessao.expire_all()
    assert sessao.get(Categoria, categoria_com_produtos.id) is not None


def teste_excluir_categoria_sem_produtos_funciona(admin_logado, sessao):
    categoria = criar_categoria(sessao, "masculino", "Cintos", "cintos")
    sessao.commit()

    assert admin_logado.delete(f"{ROTA}/{categoria.id}").status_code == 200
    sessao.expire_all()
    assert sessao.get(Categoria, categoria.id) is None


def teste_listagem_filtra_por_colecao_e_conta_produtos(
    admin_logado, sessao, categoria_com_produtos, colecoes
):
    criar_categoria(sessao, "masculino", "Sapatos", "sapatos")
    sessao.commit()

    todas = admin_logado.get(ROTA).json()
    so_feminino = admin_logado.get(ROTA, params={"colecaoId": colecoes["feminino"]}).json()

    assert {c["colecaoSlug"] for c in todas} == {"feminino", "masculino"}
    assert {c["colecaoSlug"] for c in so_feminino} == {"feminino"}
    assert [c for c in todas if c["slug"] == "bolsas"][0]["totalProdutos"] == 4
    assert [c for c in todas if c["slug"] == "sapatos"][0]["totalProdutos"] == 0


def teste_categoria_inexistente_responde_404(admin_logado):
    assert admin_logado.patch(f"{ROTA}/99999", json={"nome": "X"}).status_code == 404
    assert admin_logado.delete(f"{ROTA}/99999").status_code == 404
