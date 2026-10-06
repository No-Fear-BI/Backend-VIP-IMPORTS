"""CRUD de produto do painel (tarefa 55).

Todas as rotas exercitadas aqui já foram provadas protegidas pela varredura de
teste_protecao_admin.py — este arquivo cuida do comportamento delas.

A exclusão de produto tem um teste de regressão próprio, junto com as outras
duas portas da mesma armadilha, em teste_admin_variacoes.py.
"""

import pytest
from sqlalchemy import func, select

from testes.fabrica import criar_categoria, criar_marca, criar_produto
from vip_api.modelos.catalogo import Produto, ProdutoImagem, ProdutoVariacao
from vip_api.modelos.cliente import CarrinhoItem
from vip_api.modelos.selecao import SelecaoItem

ROTA = "/api/v1/admin/produtos"


@pytest.fixture
def marca_e_categoria(sessao):
    marca = criar_marca(sessao, "Chanel", "chanel")
    categoria = criar_categoria(sessao, "feminino", "Bolsas", "bolsas")
    sessao.commit()
    return marca, categoria


# ======================================================================
# Criar
# ======================================================================


def teste_criar_com_codigo_informado(admin_logado, marca_e_categoria):
    marca, categoria = marca_e_categoria

    resposta = admin_logado.post(
        ROTA,
        json={
            "codigo": "chn-9001",
            "nome": "Bolsa Clássica",
            "marcaId": marca.id,
            "categoriaId": categoria.id, "publicos": ["feminino"],
        },
    )

    assert resposta.status_code == 201
    corpo = resposta.json()
    # Guardado em maiúsculas, como o resto do catálogo.
    assert corpo["codigo"] == "CHN-9001"
    assert corpo["status"] == "normal"
    assert corpo["publicos"] == ["feminino"]


def teste_criar_sem_codigo_gera_no_padrao_da_marca(admin_logado, marca_e_categoria):
    """Marca ainda sem produto: o prefixo sai do nome (Chanel -> CHN)."""
    marca, categoria = marca_e_categoria

    resposta = admin_logado.post(
        ROTA, json={"nome": "Bolsa Nova", "marcaId": marca.id, "categoriaId": categoria.id, "publicos": ["feminino"]}
    )

    assert resposta.status_code == 201
    assert resposta.json()["codigo"] == "CHN-0001"


def teste_codigo_gerado_continua_a_sequencia_da_marca(
    admin_logado, sessao, marca_e_categoria
):
    """Com produto já cadastrado, o gerador segue o prefixo E o número que a
    marca já usa — é o que evita a mesma marca com dois padrões de código."""
    marca, categoria = marca_e_categoria
    criar_produto(sessao, "CHN-0041", "Bolsa Anterior", marca, categoria, com_imagem=False)
    sessao.commit()

    resposta = admin_logado.post(
        ROTA, json={"nome": "Bolsa Seguinte", "marcaId": marca.id, "categoriaId": categoria.id, "publicos": ["feminino"]}
    )

    assert resposta.status_code == 201
    assert resposta.json()["codigo"] == "CHN-0042"


def teste_criar_com_codigo_repetido_responde_409(admin_logado, sessao, marca_e_categoria):
    marca, categoria = marca_e_categoria
    criar_produto(sessao, "CHN-0100", "Bolsa Existente", marca, categoria, com_imagem=False)
    sessao.commit()

    resposta = admin_logado.post(
        ROTA,
        json={
            "codigo": "CHN-0100",
            "nome": "Outra Bolsa",
            "marcaId": marca.id,
            "categoriaId": categoria.id, "publicos": ["feminino"],
        },
    )

    assert resposta.status_code == 409
    assert resposta.json()["erro"]["codigo"] == "CODIGO_EM_USO"
    assert "codigo" in resposta.json()["erro"]["campos"]


def teste_criar_com_marca_inexistente_responde_400(admin_logado, marca_e_categoria):
    _, categoria = marca_e_categoria

    resposta = admin_logado.post(
        ROTA, json={"nome": "Sem Marca", "marcaId": 99_999, "categoriaId": categoria.id, "publicos": ["feminino"]}
    )

    assert resposta.status_code == 400
    assert "marcaId" in resposta.json()["erro"]["campos"]


# ======================================================================
# Editar
# ======================================================================


def teste_editar_muda_so_o_que_veio(admin_logado, sessao, marca_e_categoria):
    marca, categoria = marca_e_categoria
    produto = criar_produto(
        sessao, "CHN-0200", "Nome Antigo", marca, categoria, com_imagem=False
    )
    produto.descricao = "descrição original"
    sessao.commit()

    resposta = admin_logado.patch(
        f"{ROTA}/{produto.id}", json={"nome": "Nome Novo", "status": "esgotado"}
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["nome"] == "Nome Novo"
    assert corpo["status"] == "esgotado"
    # Campo ausente no corpo não muda.
    assert corpo["descricao"] == "descrição original"
    assert corpo["codigo"] == "CHN-0200"


def teste_origem_url_entra_na_criacao_e_volta_no_detalhe(admin_logado, marca_e_categoria):
    marca, categoria = marca_e_categoria
    link = "https://exemplo.x.yupoo.com/albums/123?uid=1"

    criado = admin_logado.post(
        ROTA,
        json={"nome": "Bolsa com Origem", "marcaId": marca.id, "categoriaId": categoria.id, "publicos": ["feminino"], "origemUrl": f"  {link}  "},
    )

    assert criado.status_code == 201
    assert criado.json()["origemUrl"] == link
    assert admin_logado.get(f"{ROTA}/{criado.json()['id']}").json()["origemUrl"] == link


def teste_listagem_traz_origem_url(admin_logado, marca_e_categoria):
    marca, categoria = marca_e_categoria
    link = "https://exemplo.com/album"
    admin_logado.post(
        ROTA,
        json={"nome": "Lista Origem", "marcaId": marca.id, "categoriaId": categoria.id, "publicos": ["feminino"], "origemUrl": link},
    )

    linhas = admin_logado.get(ROTA, params={"busca": "Lista Origem"}).json()["dados"]

    assert [linha["origemUrl"] for linha in linhas] == [link]


def teste_origem_url_e_opcional_e_vem_nula(admin_logado, marca_e_categoria):
    marca, categoria = marca_e_categoria

    criado = admin_logado.post(
        ROTA, json={"nome": "Sem Origem", "marcaId": marca.id, "categoriaId": categoria.id, "publicos": ["feminino"]}
    )

    assert criado.status_code == 201
    assert criado.json()["origemUrl"] is None


@pytest.mark.parametrize("invalido", ["yupoo.com/album", "ftp://x.com/a", "https://com espaco.com", "javascript:alert(1)"])
def teste_origem_url_que_nao_e_link_http_responde_400(admin_logado, marca_e_categoria, invalido):
    marca, categoria = marca_e_categoria

    resposta = admin_logado.post(
        ROTA,
        json={"nome": "Link Ruim", "marcaId": marca.id, "categoriaId": categoria.id, "publicos": ["feminino"], "origemUrl": invalido},
    )

    assert resposta.status_code in (400, 422)
    assert "origemUrl" in str(resposta.json())


def teste_editar_origem_url_muda_e_apaga(admin_logado, marca_e_categoria):
    marca, categoria = marca_e_categoria
    criado = admin_logado.post(
        ROTA, json={"nome": "Editar Origem", "marcaId": marca.id, "categoriaId": categoria.id, "publicos": ["feminino"]}
    ).json()

    mudou = admin_logado.patch(f"{ROTA}/{criado['id']}", json={"origemUrl": "https://exemplo.com/a"})
    # Outro campo no corpo não pode apagar o link: ausência é "não mexer".
    intacto = admin_logado.patch(f"{ROTA}/{criado['id']}", json={"nome": "Editar Origem 2"})
    apagou = admin_logado.patch(f"{ROTA}/{criado['id']}", json={"origemUrl": ""})

    assert mudou.json()["origemUrl"] == "https://exemplo.com/a"
    assert intacto.json()["origemUrl"] == "https://exemplo.com/a"
    assert apagou.json()["origemUrl"] is None


def teste_editar_nome_atualiza_a_ordenacao(admin_logado, sessao, marca_e_categoria):
    """`nome_ordenacao` é preenchida por listener do modelo. Se a edição
    passasse por `update()` do Core, o produto ficaria ordenado pelo nome
    velho no site."""
    marca, categoria = marca_e_categoria
    produto = criar_produto(sessao, "CHN-0201", "Zebra", marca, categoria, com_imagem=False)
    sessao.commit()

    admin_logado.patch(f"{ROTA}/{produto.id}", json={"nome": "Ábaco"})

    sessao.expire_all()
    assert sessao.get(Produto, produto.id).nome_ordenacao == "abaco"


def teste_editar_codigo_para_um_existente_responde_409(
    admin_logado, sessao, marca_e_categoria
):
    marca, categoria = marca_e_categoria
    ocupado = criar_produto(sessao, "CHN-0300", "Ocupado", marca, categoria, com_imagem=False)
    alvo = criar_produto(sessao, "CHN-0301", "Alvo", marca, categoria, com_imagem=False)
    sessao.commit()

    resposta = admin_logado.patch(f"{ROTA}/{alvo.id}", json={"codigo": ocupado.codigo})

    assert resposta.status_code == 409
    assert resposta.json()["erro"]["codigo"] == "CODIGO_EM_USO"
    sessao.expire_all()
    assert sessao.get(Produto, alvo.id).codigo == "CHN-0301"


def teste_editar_produto_inexistente_responde_404(admin_logado):
    resposta = admin_logado.patch(f"{ROTA}/99999", json={"nome": "Qualquer"})

    assert resposta.status_code == 404
    assert resposta.json()["erro"]["codigo"] == "PRODUTO_NAO_ENCONTRADO"


# ======================================================================
# Excluir
# ======================================================================


def teste_excluir_leva_o_carrinho_e_preserva_a_selecao(
    admin_logado, cliente_logado, sessao, produto_com_variacoes
):
    """O item do carrinho é dado VIVO e some com o produto; a linha da seleção
    é histórico CONGELADO e fica, com `produto_id` nulo e o texto intacto."""
    produto = produto_com_variacoes
    tamanho = sessao.scalar(
        select(ProdutoVariacao.id).where(
            ProdutoVariacao.produto_id == produto.id, ProdutoVariacao.tipo == "tamanho"
        )
    )
    cor = sessao.scalar(
        select(ProdutoVariacao.id).where(
            ProdutoVariacao.produto_id == produto.id, ProdutoVariacao.tipo == "cor"
        )
    )
    cliente_logado.post(
        "/api/v1/carrinho",
        json={"produtoId": produto.id, "variacaoTamanhoId": tamanho, "variacaoCorId": cor},
    )
    assert cliente_logado.post("/api/v1/selecoes").status_code == 201

    antes_carrinho = sessao.scalar(
        select(CarrinhoItem.id).where(CarrinhoItem.produto_id == produto.id)
    )
    antes_selecao = sessao.scalar(
        select(SelecaoItem.id).where(SelecaoItem.produto_id == produto.id)
    )
    assert antes_carrinho is not None and antes_selecao is not None

    resposta = admin_logado.delete(f"{ROTA}/{produto.id}")
    assert resposta.status_code == 200

    sessao.expire_all()
    assert sessao.get(Produto, produto.id) is None
    assert sessao.scalar(select(CarrinhoItem.id).where(CarrinhoItem.id == antes_carrinho)) is None

    item = sessao.get(SelecaoItem, antes_selecao)
    assert item is not None
    assert item.produto_id is None
    assert item.produto_codigo == "TST-PAR"
    assert item.produto_nome == "Bolsa Clássica Chanel"
    assert item.variacao_tamanho == "M"
    assert item.variacao_cor == "Preto"


def teste_excluir_leva_imagens_e_variacoes(admin_logado, sessao, produto_com_variacoes):
    produto_id = produto_com_variacoes.id

    admin_logado.delete(f"{ROTA}/{produto_id}")

    sessao.expire_all()
    assert sessao.scalars(
        select(ProdutoImagem.id).where(ProdutoImagem.produto_id == produto_id)
    ).all() == []
    assert sessao.scalars(
        select(ProdutoVariacao.id).where(ProdutoVariacao.produto_id == produto_id)
    ).all() == []


# ======================================================================
# Duplicar
# ======================================================================


def teste_duplicar_copia_imagens_e_variacoes(admin_logado, sessao, marca_e_categoria):
    marca, categoria = marca_e_categoria
    original = criar_produto(
        sessao,
        "CHN-0400",
        "Bolsa Original",
        marca,
        categoria,
        variacoes=[("tamanho", "M"), ("tamanho", "G"), ("cor", "Preto")],
    )
    sessao.add(
        ProdutoImagem(produto_id=original.id, url="https://exemplo.test/2.jpg", ordem=2)
    )
    sessao.commit()

    resposta = admin_logado.post(f"{ROTA}/{original.id}/duplicar")

    assert resposta.status_code == 201
    copia = resposta.json()
    assert copia["id"] != original.id
    assert copia["codigo"] != original.codigo
    assert copia["nome"] == "Bolsa Original (cópia)"
    # Nasce oculta: é rascunho até alguém terminar de editar.
    assert copia["status"] == "oculto"
    assert [i["ordem"] for i in copia["imagens"]] == [1, 2]
    assert [i["url"] for i in copia["imagens"]] == [
        "https://exemplo.test/CHN-0400.jpg",
        "https://exemplo.test/2.jpg",
    ]
    assert {(v["tipo"], v["valor"]) for v in copia["variacoes"]} == {
        ("tamanho", "M"),
        ("tamanho", "G"),
        ("cor", "Preto"),
    }


def teste_duplicar_nao_mexe_no_original(admin_logado, sessao, marca_e_categoria):
    marca, categoria = marca_e_categoria
    original = criar_produto(sessao, "CHN-0401", "Intocada", marca, categoria)
    sessao.commit()

    admin_logado.post(f"{ROTA}/{original.id}/duplicar")

    sessao.expire_all()
    de_novo = sessao.get(Produto, original.id)
    assert de_novo.nome == "Intocada"
    assert de_novo.status == "normal"
    assert (
        len(sessao.scalars(select(ProdutoImagem.id).where(ProdutoImagem.produto_id == original.id)).all())
        == 1
    )


# ======================================================================
# Lote
# ======================================================================


def teste_lote_altera_todos_os_ids(admin_logado, sessao, catalogo):
    ids = [produto.id for produto in catalogo.visiveis[:5]]

    resposta = admin_logado.patch(
        f"{ROTA}/lote", json={"ids": ids, "status": "esgotado", "destaque": True}
    )

    assert resposta.status_code == 200
    assert resposta.json()["alterados"] == 5

    sessao.expire_all()
    alterados = sessao.scalars(select(Produto).where(Produto.id.in_(ids))).all()
    assert {p.status for p in alterados} == {"esgotado"}
    assert all(p.destaque for p in alterados)
    # ck_produtos_destaque_ordem: destaque ligado exige ordem, e a rota
    # preenche sozinha em vez de recusar o salvamento.
    assert all(p.destaque_ordem is not None for p in alterados)


def teste_lote_com_id_inexistente_nao_altera_nada(admin_logado, sessao, catalogo):
    ids = [catalogo.visiveis[0].id, 99_999_999, catalogo.visiveis[1].id]
    antes = {
        produto.id: produto.status for produto in catalogo.visiveis[:2]
    }

    resposta = admin_logado.patch(f"{ROTA}/lote", json={"ids": ids, "status": "oculto"})

    assert resposta.status_code == 404
    erro = resposta.json()["erro"]
    assert erro["codigo"] == "PRODUTO_NAO_ENCONTRADO"
    assert erro["detalhes"]["naoEncontrados"] == [99_999_999]

    sessao.expire_all()
    for identificador, status in antes.items():
        assert sessao.get(Produto, identificador).status == status


def teste_lote_com_campo_fora_da_lista_responde_400(admin_logado, catalogo):
    resposta = admin_logado.patch(
        f"{ROTA}/lote",
        json={"ids": [catalogo.visiveis[0].id], "nome": "Renomeando em lote"},
    )

    assert resposta.status_code == 400
    assert resposta.json()["erro"]["codigo"] == "DADOS_INVALIDOS"
    assert "nome" in resposta.json()["erro"]["campos"]


def teste_lote_troca_categoria_sem_mexer_no_publico(admin_logado, sessao, catalogo):
    """Desde a 0015 a categoria não tem coleção: trocar a categoria em lote não muda o
    público do produto (feminino/masculino)."""
    do_feminino = [p for p in catalogo.visiveis if p.feminino]
    destino = catalogo.categorias[1]  # Sapatos
    ids = [p.id for p in do_feminino[:3]]

    resposta = admin_logado.patch(f"{ROTA}/lote", json={"ids": ids, "categoriaId": destino.id})

    assert resposta.status_code == 200
    sessao.expire_all()
    for identificador in ids:
        produto = sessao.get(Produto, identificador)
        assert produto.categoria_id == destino.id
        assert produto.feminino and not produto.masculino


def teste_lote_acima_do_teto_responde_400(admin_logado):
    from vip_api.esquemas.admin_produto import LIMITE_LOTE

    resposta = admin_logado.patch(
        f"{ROTA}/lote", json={"ids": list(range(1, LIMITE_LOTE + 2)), "status": "oculto"}
    )

    assert resposta.status_code == 400


# ======================================================================
# Listagem
# ======================================================================


def teste_listagem_inclui_ocultos_por_padrao(admin_logado, catalogo):
    resposta = admin_logado.get(ROTA, params={"porPagina": 100})

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["paginacao"]["total"] == len(catalogo.visiveis) + len(catalogo.ocultos)
    assert "oculto" in {item["status"] for item in corpo["dados"]}


def teste_filtro_de_status_separa(admin_logado, catalogo):
    resposta = admin_logado.get(ROTA, params={"status": "oculto", "porPagina": 100})

    corpo = resposta.json()
    assert corpo["paginacao"]["total"] == len(catalogo.ocultos)
    assert {item["status"] for item in corpo["dados"]} == {"oculto"}
    assert {item["id"] for item in corpo["dados"]} == catalogo.ids_ocultos


def teste_busca_por_codigo_e_por_nome(admin_logado, sessao, marca_e_categoria):
    marca, categoria = marca_e_categoria
    criar_produto(sessao, "CHN-7777", "Bolsa Matelassê", marca, categoria, com_imagem=False)
    criar_produto(sessao, "CHN-8888", "Sapato Camurça", marca, categoria, com_imagem=False)
    sessao.commit()

    por_codigo = admin_logado.get(ROTA, params={"busca": "chn-7777"}).json()
    por_nome = admin_logado.get(ROTA, params={"busca": "matelasse"}).json()

    assert [item["codigo"] for item in por_codigo["dados"]] == ["CHN-7777"]
    assert [item["codigo"] for item in por_nome["dados"]] == ["CHN-7777"]


def teste_paginacao_por_pagina_e_total(admin_logado, catalogo):
    total_esperado = len(catalogo.visiveis) + len(catalogo.ocultos)

    primeira = admin_logado.get(ROTA, params={"pagina": 1, "porPagina": 25}).json()
    segunda = admin_logado.get(ROTA, params={"pagina": 2, "porPagina": 25}).json()
    ultima = admin_logado.get(ROTA, params={"pagina": 3, "porPagina": 25}).json()

    assert primeira["paginacao"] == {"total": total_esperado, "porPagina": 25, "pagina": 1}
    assert len(primeira["dados"]) == 25
    assert len(segunda["dados"]) == 25
    assert len(ultima["dados"]) == total_esperado - 50

    ids = [item["id"] for item in primeira["dados"] + segunda["dados"] + ultima["dados"]]
    assert len(ids) == len(set(ids)) == total_esperado


def teste_detalhe_por_id_traz_imagens_e_variacoes(admin_logado, produto_com_variacoes):
    resposta = admin_logado.get(f"{ROTA}/{produto_com_variacoes.id}")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["codigo"] == "TST-PAR"
    assert len(corpo["imagens"]) == 1
    assert {(v["tipo"], v["valor"]) for v in corpo["variacoes"]} == {
        ("tamanho", "M"),
        ("cor", "Preto"),
    }


# ======================================================================
# Contagem da paginação
# ======================================================================


def teste_total_da_listagem_respeita_os_filtros(admin_logado, sessao, catalogo):
    """O `total` sai de um COUNT que passa pelos MESMOS filtros da página. Um
    COUNT sem WHERE faria a tela oferecer páginas que não existem — a de número
    3 de um filtro que só tem 12 resultados."""
    marca = catalogo.marcas[0]
    esperado = sessao.scalar(
        select(func.count())
        .select_from(Produto)
        .where(Produto.marca_id == marca.id, Produto.status == "oculto")
    )
    assert esperado > 0

    resposta = admin_logado.get(
        ROTA, params={"marcaId": marca.id, "status": "oculto", "porPagina": 100}
    )

    corpo = resposta.json()
    assert corpo["paginacao"]["total"] == esperado
    assert len(corpo["dados"]) == esperado


def teste_total_da_busca_respeita_o_termo(admin_logado, sessao, marca_e_categoria):
    marca, categoria = marca_e_categoria
    for indice in range(3):
        criar_produto(
            sessao, f"CHN-81{indice:02d}", f"Bolsa Matelassê {indice}", marca, categoria,
            com_imagem=False,
        )
    criar_produto(sessao, "CHN-8200", "Sapato Camurça", marca, categoria, com_imagem=False)
    sessao.commit()

    corpo = admin_logado.get(ROTA, params={"busca": "matelasse"}).json()

    assert corpo["paginacao"]["total"] == 3
    assert len(corpo["dados"]) == 3


# ======================================================================
# Preço interno (só do painel, em centavos) — opcional, de 0 a R$ 100.000,00
# ======================================================================


def _corpo_novo(marca, categoria, **extra):
    return {"nome": "Bolsa com Preço", "marcaId": marca.id, "categoriaId": categoria.id, "publicos": ["feminino"], **extra}


def teste_criar_sem_preco_guarda_vazio(admin_logado, marca_e_categoria):
    marca, categoria = marca_e_categoria
    resposta = admin_logado.post(ROTA, json=_corpo_novo(marca, categoria))
    assert resposta.status_code == 201
    assert resposta.json()["precoCentavos"] is None


def teste_criar_com_preco_valido(admin_logado, marca_e_categoria):
    marca, categoria = marca_e_categoria
    resposta = admin_logado.post(ROTA, json=_corpo_novo(marca, categoria, precoCentavos=123450))
    assert resposta.status_code == 201
    assert resposta.json()["precoCentavos"] == 123450


def teste_criar_com_preco_zero_e_aceito(admin_logado, marca_e_categoria):
    marca, categoria = marca_e_categoria
    resposta = admin_logado.post(ROTA, json=_corpo_novo(marca, categoria, precoCentavos=0))
    assert resposta.status_code == 201
    assert resposta.json()["precoCentavos"] == 0


@pytest.mark.parametrize("invalido", [-1, -5000, 10_000_001, "abc", 12.5])
def teste_criar_com_preco_invalido_da_400(admin_logado, marca_e_categoria, invalido):
    marca, categoria = marca_e_categoria
    resposta = admin_logado.post(ROTA, json=_corpo_novo(marca, categoria, precoCentavos=invalido))
    assert resposta.status_code == 400
    assert "precoCentavos" in resposta.json()["erro"]["campos"]


def teste_editar_preco_e_apagar_com_null(admin_logado, marca_e_categoria):
    marca, categoria = marca_e_categoria
    criado = admin_logado.post(ROTA, json=_corpo_novo(marca, categoria)).json()
    url = f"{ROTA}/{criado['id']}"

    editado = admin_logado.patch(url, json={"precoCentavos": 99900})
    assert editado.status_code == 200
    assert editado.json()["precoCentavos"] == 99900

    # PATCH sem o campo não mexe no preço.
    admin_logado.patch(url, json={"nome": "Outro nome"})
    assert admin_logado.get(url).json()["precoCentavos"] == 99900

    apagado = admin_logado.patch(url, json={"precoCentavos": None})
    assert apagado.status_code == 200
    assert apagado.json()["precoCentavos"] is None


def teste_editar_com_preco_negativo_da_400_e_nao_altera(admin_logado, marca_e_categoria):
    marca, categoria = marca_e_categoria
    criado = admin_logado.post(ROTA, json=_corpo_novo(marca, categoria, precoCentavos=5000)).json()
    resposta = admin_logado.patch(f"{ROTA}/{criado['id']}", json={"precoCentavos": -100})
    assert resposta.status_code == 400
    assert admin_logado.get(f"{ROTA}/{criado['id']}").json()["precoCentavos"] == 5000


def teste_listagem_do_painel_traz_o_preco(admin_logado, marca_e_categoria):
    marca, categoria = marca_e_categoria
    admin_logado.post(ROTA, json=_corpo_novo(marca, categoria, precoCentavos=45000))
    dados = admin_logado.get(ROTA).json()["dados"]
    assert dados[0]["precoCentavos"] == 45000


def teste_duplicar_leva_o_preco(admin_logado, marca_e_categoria):
    marca, categoria = marca_e_categoria
    criado = admin_logado.post(ROTA, json=_corpo_novo(marca, categoria, precoCentavos=45000)).json()
    copia = admin_logado.post(f"{ROTA}/{criado['id']}/duplicar")
    assert copia.status_code == 201
    assert copia.json()["precoCentavos"] == 45000
