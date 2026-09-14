"""Destaques da home pelo painel (tarefa 58)."""

import pytest
from sqlalchemy import select

from testes.fabrica import criar_categoria, criar_marca, criar_produto
from vip_api.modelos.catalogo import Categoria, Produto
from vip_api.servicos.admin_destaques import LIMITE_CATEGORIAS_DESTAQUE
from vip_api.servicos.home import LIMITE_DESTAQUES

PRODUTOS = "/api/v1/admin/destaques/produtos"
CATEGORIAS = "/api/v1/admin/destaques/categorias"


@pytest.fixture
def seis_produtos(sessao):
    marca = criar_marca(sessao, "Chanel", "chanel")
    categoria = criar_categoria(sessao, "feminino", "Bolsas", "bolsas")
    produtos = [
        criar_produto(sessao, f"CHN-D{indice:03d}", f"Bolsa {indice}", marca, categoria)
        for indice in range(6)
    ]
    sessao.commit()
    return produtos


def destaques_no_banco(sessao) -> list[tuple[int, int]]:
    return [
        (produto.id, produto.destaque_ordem)
        for produto in sessao.scalars(
            select(Produto)
            .where(Produto.destaque.is_(True))
            .order_by(Produto.destaque_ordem, Produto.id)
        )
    ]


def teste_definir_substitui_o_conjunto(admin_logado, sessao, seis_produtos):
    primeira = [seis_produtos[0].id, seis_produtos[1].id, seis_produtos[2].id]
    admin_logado.patch(PRODUTOS, json={"ids": primeira})

    segunda = [seis_produtos[3].id, seis_produtos[0].id]
    resposta = admin_logado.patch(PRODUTOS, json={"ids": segunda})

    assert resposta.status_code == 200
    assert resposta.json() == segunda
    sessao.expire_all()
    # Quem saiu da lista deixou de ser destaque; a ordem é a da posição.
    assert destaques_no_banco(sessao) == [(segunda[0], 1), (segunda[1], 2)]


def teste_a_ordem_segue_a_posicao_da_lista(admin_logado, sessao, seis_produtos):
    ordem = [seis_produtos[4].id, seis_produtos[1].id, seis_produtos[5].id]

    admin_logado.patch(PRODUTOS, json={"ids": ordem})

    sessao.expire_all()
    assert [identificador for identificador, _ in destaques_no_banco(sessao)] == ordem
    assert [posicao for _, posicao in destaques_no_banco(sessao)] == [1, 2, 3]


def teste_lista_vazia_tira_todos(admin_logado, sessao, seis_produtos):
    admin_logado.patch(PRODUTOS, json={"ids": [p.id for p in seis_produtos[:3]]})

    resposta = admin_logado.patch(PRODUTOS, json={"ids": []})

    assert resposta.status_code == 200
    sessao.expire_all()
    assert destaques_no_banco(sessao) == []


def teste_produto_oculto_recusado_com_os_ids(admin_logado, sessao, seis_produtos):
    """Oculto some da home inteira: aceitar a marcação faria o cliente marcar,
    não ver nada e procurar o erro na tela errada."""
    ocultos = seis_produtos[1], seis_produtos[3]
    for produto in ocultos:
        produto.status = "oculto"
    sessao.commit()

    resposta = admin_logado.patch(
        PRODUTOS, json={"ids": [seis_produtos[0].id, ocultos[0].id, ocultos[1].id]}
    )

    assert resposta.status_code == 400
    erro = resposta.json()["erro"]
    assert erro["codigo"] == "DADOS_INVALIDOS"
    assert erro["detalhes"]["ocultos"] == [ocultos[0].id, ocultos[1].id]
    for identificador in (ocultos[0].id, ocultos[1].id):
        assert str(identificador) in erro["mensagem"]
    # Nada foi aplicado.
    sessao.expire_all()
    assert destaques_no_banco(sessao) == []


def teste_produto_inexistente_recusado(admin_logado, seis_produtos):
    resposta = admin_logado.patch(PRODUTOS, json={"ids": [seis_produtos[0].id, 999_999]})

    assert resposta.status_code == 400
    assert resposta.json()["erro"]["detalhes"]["naoEncontrados"] == [999_999]


def teste_teto_de_produtos(admin_logado, sessao, seis_produtos):
    """O teto é o mesmo número que a home renderiza: marcar mais do que ela
    mostra é marcar o que ninguém vai ver."""
    marca = criar_marca(sessao, "Gucci", "gucci")
    categoria = criar_categoria(sessao, "masculino", "Sapatos", "sapatos")
    extras = [
        criar_produto(sessao, f"GUC-D{i:03d}", f"Sapato {i}", marca, categoria)
        for i in range(LIMITE_DESTAQUES)
    ]
    sessao.commit()

    ids = [p.id for p in seis_produtos + extras][: LIMITE_DESTAQUES + 1]
    resposta = admin_logado.patch(PRODUTOS, json={"ids": ids})

    assert resposta.status_code == 400
    assert str(LIMITE_DESTAQUES) in resposta.json()["erro"]["mensagem"]


def teste_id_repetido_recusado(admin_logado, seis_produtos):
    repetido = seis_produtos[0].id
    resposta = admin_logado.patch(PRODUTOS, json={"ids": [repetido, repetido]})

    assert resposta.status_code == 400


def teste_home_devolve_os_destaques_na_ordem_definida(
    admin_logado, sem_sessao, sessao, seis_produtos
):
    ordem = [seis_produtos[2].id, seis_produtos[0].id, seis_produtos[4].id]

    admin_logado.patch(PRODUTOS, json={"ids": ordem})

    home = sem_sessao.get("/api/v1/home").json()
    assert [item["id"] for item in home["destaques"]] == ordem


def teste_categorias_substituem_o_conjunto(admin_logado, sessao):
    primeira = criar_categoria(sessao, "feminino", "Bolsas", "bolsas")
    segunda = criar_categoria(sessao, "masculino", "Sapatos", "sapatos")
    terceira = criar_categoria(sessao, "feminino", "Vestidos", "vestidos")
    sessao.commit()

    admin_logado.patch(CATEGORIAS, json={"ids": [primeira.id, segunda.id]})
    resposta = admin_logado.patch(CATEGORIAS, json={"ids": [terceira.id, primeira.id]})

    assert resposta.status_code == 200
    sessao.expire_all()
    em_destaque = [
        (c.id, c.destaque_ordem)
        for c in sessao.scalars(
            select(Categoria)
            .where(Categoria.destaque.is_(True))
            .order_by(Categoria.destaque_ordem)
        )
    ]
    assert em_destaque == [(terceira.id, 1), (primeira.id, 2)]


def teste_categoria_inativa_recusada(admin_logado, sessao):
    categoria = criar_categoria(sessao, "feminino", "Bolsas", "bolsas")
    categoria.ativa = False
    sessao.commit()

    resposta = admin_logado.patch(CATEGORIAS, json={"ids": [categoria.id]})

    assert resposta.status_code == 400
    assert resposta.json()["erro"]["detalhes"]["inativas"] == [categoria.id]


def teste_teto_de_categorias(admin_logado, sessao):
    categorias = [
        criar_categoria(sessao, "feminino", f"Categoria {i}", f"categoria-{i}")
        for i in range(LIMITE_CATEGORIAS_DESTAQUE + 1)
    ]
    sessao.commit()

    resposta = admin_logado.patch(CATEGORIAS, json={"ids": [c.id for c in categorias]})

    assert resposta.status_code == 400
    assert str(LIMITE_CATEGORIAS_DESTAQUE) in resposta.json()["erro"]["mensagem"]


def teste_home_devolve_as_categorias_na_ordem_definida(admin_logado, sem_sessao, sessao):
    primeira = criar_categoria(sessao, "masculino", "Sapatos", "sapatos")
    segunda = criar_categoria(sessao, "feminino", "Bolsas", "bolsas")
    sessao.commit()

    admin_logado.patch(CATEGORIAS, json={"ids": [primeira.id, segunda.id]})

    home = sem_sessao.get("/api/v1/home").json()
    assert [c["id"] for c in home["categoriasDestaque"]] == [primeira.id, segunda.id]


def teste_home_continua_em_quatro_consultas(
    admin_logado, sem_sessao, sessao, seis_produtos, contar_consultas
):
    """O orçamento da home é de quatro consultas — banners, destaques,
    categorias em destaque e marcas. Definir destaques pelo painel não pode ter
    acrescentado nenhuma: a home é a rota mais chamada do site."""
    admin_logado.patch(PRODUTOS, json={"ids": [p.id for p in seis_produtos[:3]]})

    with contar_consultas() as consultas:
        sem_sessao.get("/api/v1/home")

    assert len(consultas) == 4, "\n".join(consultas)
