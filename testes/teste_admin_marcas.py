"""CRUD de marcas no painel (tarefa 57).

O que mais importa aqui é o slug: ele é a URL pública da marca, com milhares
de produtos pendurados, e não pode mudar porque alguém corrigiu a caixa alta
do nome na tela.
"""

import pytest
from sqlalchemy import func, select

from testes.fabrica import criar_categoria, criar_marca, criar_produto
from vip_api.modelos.catalogo import Marca, Produto

ROTA = "/api/v1/admin/marcas"


@pytest.fixture
def marca_com_produtos(sessao):
    marca = criar_marca(sessao, "Chanel", "chanel")
    categoria = criar_categoria(sessao, "feminino", "Bolsas", "bolsas")
    for indice in range(3):
        criar_produto(
            sessao, f"CHN-90{indice:02d}", f"Bolsa {indice}", marca, categoria, com_imagem=False
        )
    sessao.commit()
    return marca


def teste_criar_gera_o_slug_a_partir_do_nome(admin_logado):
    resposta = admin_logado.post(ROTA, json={"nome": "Louis Vuitton"})

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["slug"] == "louis-vuitton"
    assert corpo["nome"] == "Louis Vuitton"
    assert corpo["totalProdutos"] == 0


def teste_criar_tira_acento_do_slug(admin_logado):
    assert admin_logado.post(ROTA, json={"nome": "Céline"}).json()["slug"] == "celine"


def teste_criar_com_slug_explicito_usa_o_informado(admin_logado):
    resposta = admin_logado.post(ROTA, json={"nome": "Yves Saint Laurent", "slug": "ysl"})

    assert resposta.json()["slug"] == "ysl"


def teste_criar_com_nome_repetido_desambigua_o_slug(admin_logado):
    """Slug gerado colide: ganha sufixo em vez de estourar. Quem não pediu slug
    nenhum não tem por que receber um erro de slug."""
    primeiro = admin_logado.post(ROTA, json={"nome": "Prada"}).json()
    segundo = admin_logado.post(ROTA, json={"nome": "Prada"}).json()

    assert primeiro["slug"] == "prada"
    assert segundo["slug"] == "prada-2"


def teste_criar_com_slug_explicito_repetido_responde_409(admin_logado, marca_com_produtos):
    resposta = admin_logado.post(ROTA, json={"nome": "Outra", "slug": "chanel"})

    assert resposta.status_code == 409
    assert resposta.json()["erro"]["codigo"] == "SLUG_EM_USO"


def teste_editar_o_nome_nao_muda_o_slug(admin_logado, sessao, marca_com_produtos):
    """A regra que protege os links já compartilhados e o que o buscador
    indexou: corrigir "chanel" para "Chanel" na tela não mexe na URL."""
    resposta = admin_logado.patch(
        f"{ROTA}/{marca_com_produtos.id}", json={"nome": "CHANEL Paris"}
    )

    assert resposta.status_code == 200
    assert resposta.json()["nome"] == "CHANEL Paris"
    assert resposta.json()["slug"] == "chanel"
    sessao.expire_all()
    assert sessao.get(Marca, marca_com_produtos.id).slug == "chanel"


def teste_editar_mandando_slug_troca_o_slug(admin_logado, marca_com_produtos):
    resposta = admin_logado.patch(
        f"{ROTA}/{marca_com_produtos.id}", json={"slug": "chanel-paris"}
    )

    assert resposta.status_code == 200
    assert resposta.json()["slug"] == "chanel-paris"


def teste_editar_slug_normaliza_o_que_veio(admin_logado, marca_com_produtos):
    """Slug informado também passa pela normalização: ninguém quer
    `/marcas/Chanel Paris` com espaço e maiúscula na URL."""
    resposta = admin_logado.patch(
        f"{ROTA}/{marca_com_produtos.id}", json={"slug": "Chanel Paris"}
    )

    assert resposta.json()["slug"] == "chanel-paris"


def teste_editar_para_slug_de_outra_marca_responde_409(admin_logado, sessao, marca_com_produtos):
    outra = criar_marca(sessao, "Gucci", "gucci")
    sessao.commit()

    resposta = admin_logado.patch(f"{ROTA}/{outra.id}", json={"slug": "chanel"})

    assert resposta.status_code == 409
    assert resposta.json()["erro"]["codigo"] == "SLUG_EM_USO"


def teste_excluir_marca_com_produtos_responde_409_com_a_contagem(
    admin_logado, sessao, marca_com_produtos
):
    real = sessao.scalar(
        select(func.count())
        .select_from(Produto)
        .where(Produto.marca_id == marca_com_produtos.id)
    )

    resposta = admin_logado.delete(f"{ROTA}/{marca_com_produtos.id}")

    assert resposta.status_code == 409
    erro = resposta.json()["erro"]
    assert erro["codigo"] == "MARCA_COM_PRODUTOS"
    assert f"{real} produtos usam esta marca" in erro["mensagem"]
    assert erro["detalhes"]["totalProdutos"] == real
    sessao.expire_all()
    assert sessao.get(Marca, marca_com_produtos.id) is not None


def teste_excluir_marca_sem_produtos_funciona(admin_logado, sessao):
    """O 409 não é um "não" permanente: sem produto pendurado, a marca sai."""
    marca = criar_marca(sessao, "Marca Vazia", "marca-vazia")
    sessao.commit()

    resposta = admin_logado.delete(f"{ROTA}/{marca.id}")

    assert resposta.status_code == 200
    sessao.expire_all()
    assert sessao.get(Marca, marca.id) is None


def teste_listagem_traz_a_contagem_de_produtos(admin_logado, sessao, marca_com_produtos):
    criar_marca(sessao, "Sem Produto", "sem-produto")
    sessao.commit()

    listagem = admin_logado.get(ROTA).json()

    por_slug = {marca["slug"]: marca["totalProdutos"] for marca in listagem}
    assert por_slug["chanel"] == 3
    assert por_slug["sem-produto"] == 0


def teste_marca_inexistente_responde_404(admin_logado):
    assert admin_logado.patch(f"{ROTA}/99999", json={"nome": "X"}).status_code == 404
    assert admin_logado.delete(f"{ROTA}/99999").status_code == 404
