"""Categoria escondida (`ativa = false`): some da vitrine sem apagar cadastro nem produto.

A categoria sai da navegação, dos destaques da home e do link direto; os produtos
continuam em /produtos, nas outras categorias deles, e editar outros campos não
falha por causa dela. Só não entra produto NOVO nela.
"""

from sqlalchemy import select

from testes.fabrica import criar_categoria, criar_marca, criar_produto
from vip_api.modelos.catalogo import Categoria

CATEGORIAS = "/api/v1/admin/categorias"
PRODUTOS = "/api/v1/admin/produtos"
PUBLICO = "/api/v1/produtos"


def _cenario(sessao):
    marca = criar_marca(sessao, "Marca Escondida", "marca-escondida")
    verao = criar_categoria(sessao, "feminino", "Coleção de verão", "colecao-de-verao")
    bolsas = criar_categoria(sessao, "feminino", "Bolsas", "bolsas")
    produto = criar_produto(sessao, "ESC-001", "Peça de verão", marca, verao, com_imagem=False)
    sessao.commit()
    return produto, verao, bolsas


def _esconder(admin_logado, categoria):
    resposta = admin_logado.patch(f"{CATEGORIAS}/{categoria.id}", json={"ativa": False})
    assert resposta.status_code == 200
    assert resposta.json()["ativa"] is False


def teste_categoria_escondida_some_da_navegacao_e_reaparece_ao_reativar(admin_logado, sem_sessao, sessao):
    _, verao, _ = _cenario(sessao)
    rota = "/api/v1/colecoes/feminino/categorias"
    assert verao.id in [c["id"] for c in sem_sessao.get(rota).json()]

    _esconder(admin_logado, verao)
    assert verao.id not in [c["id"] for c in sem_sessao.get(rota).json()]
    # O painel continua vendo: é de lá que ela é reativada.
    assert verao.id in [c["id"] for c in admin_logado.get(CATEGORIAS).json()]

    admin_logado.patch(f"{CATEGORIAS}/{verao.id}", json={"ativa": True})
    assert verao.id in [c["id"] for c in sem_sessao.get(rota).json()]


def teste_categoria_escondida_sai_dos_destaques_da_home(admin_logado, sem_sessao, sessao):
    _, verao, _ = _cenario(sessao)
    assert admin_logado.patch(
        "/api/v1/admin/destaques/categorias", json={"ids": [verao.id]}
    ).status_code == 200
    assert [c["id"] for c in sem_sessao.get("/api/v1/home").json()["categoriasDestaque"]] == [verao.id]

    _esconder(admin_logado, verao)
    assert sem_sessao.get("/api/v1/home").json()["categoriasDestaque"] == []


def teste_link_direto_de_categoria_escondida_responde_como_slug_desconhecido(
    admin_logado, sem_sessao, sessao
):
    produto, verao, _ = _cenario(sessao)
    params = {"colecao": "feminino", "categoria": verao.slug}
    assert [p["id"] for p in sem_sessao.get(PUBLICO, params=params).json()["dados"]] == [produto.id]

    _esconder(admin_logado, verao)
    desconhecida = sem_sessao.get(
        PUBLICO, params={"colecao": "feminino", "categoria": "nao-existe"}
    ).json()
    escondida = sem_sessao.get(PUBLICO, params=params).json()
    assert escondida == desconhecida
    assert escondida["dados"] == []

    # Os produtos continuam visíveis fora da página da categoria.
    assert [p["id"] for p in sem_sessao.get(PUBLICO).json()["dados"]] == [produto.id]
    assert [p["id"] for p in sem_sessao.get(PUBLICO, params={"colecao": "feminino"}).json()["dados"]] == [produto.id]
    assert [p["id"] for p in sem_sessao.get(PUBLICO, params={"busca": "verão"}).json()["dados"]] == [produto.id]


def teste_editar_outros_campos_de_produto_em_categoria_escondida_funciona(admin_logado, sessao):
    produto, verao, _ = _cenario(sessao)
    _esconder(admin_logado, verao)

    resposta = admin_logado.patch(f"{PRODUTOS}/{produto.id}", json={"nome": "Nome novo"})
    assert resposta.status_code == 200

    # Reenviar a lista com a categoria que o produto JÁ tem também passa...
    resposta = admin_logado.patch(f"{PRODUTOS}/{produto.id}", json={"categoriasIds": [verao.id]})
    assert resposta.status_code == 200
    # ...e o PATCH legado por categoriaId igual à atual.
    resposta = admin_logado.patch(f"{PRODUTOS}/{produto.id}", json={"categoriaId": verao.id})
    assert resposta.status_code == 200


def teste_adicionar_categoria_mantem_a_escondida_que_ja_estava(admin_logado, sessao):
    produto, verao, bolsas = _cenario(sessao)
    _esconder(admin_logado, verao)

    resposta = admin_logado.patch(
        f"{PRODUTOS}/{produto.id}", json={"categoriasIds": [verao.id, bolsas.id]}
    )
    assert resposta.status_code == 200
    assert resposta.json()["categoriasIds"] == [verao.id, bolsas.id]


def teste_categoria_escondida_nao_recebe_produto_novo(admin_logado, sessao):
    produto, verao, bolsas = _cenario(sessao)
    _esconder(admin_logado, bolsas)

    por_destinos = admin_logado.patch(f"{PRODUTOS}/{produto.id}", json={"categoriasIds": [bolsas.id]})
    por_id = admin_logado.patch(f"{PRODUTOS}/{produto.id}", json={"categoriaId": bolsas.id})
    em_lote = admin_logado.patch(f"{PRODUTOS}/lote", json={"ids": [produto.id], "categoriaId": bolsas.id})
    assert {por_destinos.status_code, por_id.status_code, em_lote.status_code} == {400}

    sessao.expire_all()
    assert sessao.scalar(select(Categoria.id).where(Categoria.id == bolsas.id)) is not None
    assert admin_logado.get(f"{PRODUTOS}/{produto.id}").json()["categoriaId"] == verao.id


def teste_lote_de_outros_campos_funciona_com_produto_em_categoria_escondida(admin_logado, sessao):
    produto, verao, _ = _cenario(sessao)
    _esconder(admin_logado, verao)

    resposta = admin_logado.patch(f"{PRODUTOS}/lote", json={"ids": [produto.id], "status": "esgotado"})
    assert resposta.status_code == 200


def teste_tema_e_categoria_comum_criar_e_atribuir_em_lote(admin_logado, sem_sessao, sessao):
    """Categoria temática é uma categoria como as outras (decisão de 30/09/2026)."""
    marca = criar_marca(sessao, "Marca Tema", "marca-tema")
    base = criar_categoria(sessao, "feminino", "Bolsas", "bolsas")
    produto = criar_produto(sessao, "TEM-001", "Bolsa tema", marca, base, com_imagem=False)
    sessao.commit()

    criada = admin_logado.post(CATEGORIAS, json={"nome": "Coleção de verão"})
    assert criada.status_code == 201, criada.text
    assert criada.json()["slug"] == "colecao-de-verao"
    assert criada.json()["ativa"] is True

    lote = admin_logado.patch(
        f"{PRODUTOS}/lote", json={"ids": [produto.id], "categoriaId": criada.json()["id"]}
    )
    assert lote.status_code == 200
    publico = sem_sessao.get(PUBLICO, params={"categoria": "colecao-de-verao"})
    assert [p["id"] for p in publico.json()["dados"]] == [produto.id]
