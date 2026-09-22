"""Vocabulário de cores no painel e filtro por cor (revisão 0007).

O CRUD em si é irmão do de marcas. O que este arquivo guarda de verdade são as
três coisas que só a cor tem:

1. Renomear a cor reescreve o texto exibido nas variações que apontam para ela
   — e para no 409 quando a UNIQUE (produto, tipo, valor) recusaria.
2. Gravar a grade de variações resolve a cor pelo SLUG, então "preto" e "Preto"
   caem na mesma linha da paleta em vez de virarem duas cores.
3. O filtro `?cor=` conta produto uma vez só, mesmo quando o produto tem a
   mesma cor em duas variações.
"""

import pytest
from sqlalchemy import select

from testes.fabrica import criar_categoria, criar_marca, criar_produto
from vip_api.modelos.catalogo import Cor, ProdutoVariacao

ROTA = "/api/v1/admin/cores"


@pytest.fixture
def produto_preto(sessao):
    marca = criar_marca(sessao, "Chanel", "chanel")
    categoria = criar_categoria(sessao, "feminino", "Bolsas", "bolsas")
    produto = criar_produto(
        sessao,
        "CHN-7001",
        "Bolsa Clássica",
        marca,
        categoria,
        com_imagem=False,
        variacoes=[("cor", "Preto"), ("tamanho", "M")],
    )
    sessao.commit()
    return produto


# ======================================================================
# CRUD
# ======================================================================


def teste_criar_gera_o_slug_a_partir_do_nome(admin_logado):
    resposta = admin_logado.post(ROTA, json={"nome": "Azul Marinho"})

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["slug"] == "azul-marinho"
    assert corpo["nome"] == "Azul Marinho"
    assert corpo["totalProdutos"] == 0


def teste_criar_tira_acento_do_slug(admin_logado):
    assert admin_logado.post(ROTA, json={"nome": "Rosé"}).json()["slug"] == "rose"


def teste_criar_com_nome_repetido_desambigua_o_slug(admin_logado):
    primeiro = admin_logado.post(ROTA, json={"nome": "Bege"}).json()
    segundo = admin_logado.post(ROTA, json={"nome": "Bege"}).json()

    assert (primeiro["slug"], segundo["slug"]) == ("bege", "bege-2")


def teste_listar_traz_a_contagem_de_produtos(admin_logado, produto_preto):
    cores = admin_logado.get(ROTA).json()

    preto = next(c for c in cores if c["slug"] == "preto")
    assert preto["totalProdutos"] == 1


def teste_editar_nao_troca_o_slug_sozinho(admin_logado, produto_preto):
    """O slug é a URL do filtro (`?cor=preto`), que pode estar compartilhada.
    Corrigir o nome na tela não pode derrubá-la."""
    cor = next(c for c in admin_logado.get(ROTA).json() if c["slug"] == "preto")

    resposta = admin_logado.patch(f"{ROTA}/{cor['id']}", json={"nome": "Preto Fosco"})

    assert resposta.status_code == 200
    assert resposta.json()["nome"] == "Preto Fosco"
    assert resposta.json()["slug"] == "preto"


def teste_excluir_cor_em_uso_responde_409_com_a_contagem(admin_logado, produto_preto):
    cor = next(c for c in admin_logado.get(ROTA).json() if c["slug"] == "preto")

    resposta = admin_logado.delete(f"{ROTA}/{cor['id']}")

    assert resposta.status_code == 409
    assert resposta.json()["erro"]["codigo"] == "COR_EM_USO"
    assert resposta.json()["erro"]["detalhes"]["totalProdutos"] == 1


def teste_excluir_cor_sem_produto_funciona(admin_logado):
    cor = admin_logado.post(ROTA, json={"nome": "Terracota"}).json()

    assert admin_logado.delete(f"{ROTA}/{cor['id']}").json() == {"ok": True}
    assert admin_logado.get(ROTA).json() == []


def teste_cor_inexistente_responde_404(admin_logado):
    resposta = admin_logado.patch(f"{ROTA}/99999", json={"nome": "Qualquer"})

    assert resposta.status_code == 404
    assert resposta.json()["erro"]["codigo"] == "COR_NAO_ENCONTRADA"


# ======================================================================
# Renomear propaga para as variações
# ======================================================================


def teste_renomear_reescreve_o_texto_das_variacoes(admin_logado, sessao, produto_preto):
    cor = next(c for c in admin_logado.get(ROTA).json() if c["slug"] == "preto")

    admin_logado.patch(f"{ROTA}/{cor['id']}", json={"nome": "Preto Fosco"})

    valor = sessao.scalar(
        select(ProdutoVariacao.valor).where(
            ProdutoVariacao.produto_id == produto_preto.id, ProdutoVariacao.tipo == "cor"
        )
    )
    assert valor == "Preto Fosco"


def teste_renomear_para_cor_que_o_produto_ja_tem_responde_409(admin_logado, sessao, produto_preto):
    """O produto fica com duas cores; renomear uma para o nome da outra
    colidiria na UNIQUE. A saída seria apagar uma variação — que pode estar no
    carrinho de alguém —, então a API recusa e diz qual produto trava."""
    admin_logado.patch(
        f"/api/v1/admin/produtos/{produto_preto.id}/variacoes",
        json={"variacoes": [{"tipo": "cor", "valor": "Preto"}, {"tipo": "cor", "valor": "Bege"}]},
    )
    bege = next(c for c in admin_logado.get(ROTA).json() if c["slug"] == "bege")

    resposta = admin_logado.patch(f"{ROTA}/{bege['id']}", json={"nome": "Preto"})

    assert resposta.status_code == 409
    assert resposta.json()["erro"]["codigo"] == "COR_EM_CONFLITO"
    assert resposta.json()["erro"]["detalhes"]["codigoProduto"] == "CHN-7001"


# ======================================================================
# Gravação da grade resolve a cor
# ======================================================================


def teste_gravar_variacao_de_cor_cria_a_cor_que_falta(admin_logado, sessao, produto_preto):
    admin_logado.patch(
        f"/api/v1/admin/produtos/{produto_preto.id}/variacoes",
        json={"variacoes": [{"tipo": "cor", "valor": "Off-White"}]},
    )

    assert sessao.scalar(select(Cor).where(Cor.slug == "off-white")) is not None


def teste_grafia_diferente_cai_na_cor_que_ja_existe(admin_logado, sessao, produto_preto):
    """"PRETO" não vira uma segunda cor: a busca é por slug."""
    admin_logado.patch(
        f"/api/v1/admin/produtos/{produto_preto.id}/variacoes",
        json={"variacoes": [{"tipo": "cor", "valor": "PRETO"}]},
    )

    cores = list(sessao.scalars(select(Cor).where(Cor.slug == "preto")))
    assert len(cores) == 1


def teste_gravar_com_cor_id_usa_o_nome_do_vocabulario(admin_logado, sessao, produto_preto):
    cor = admin_logado.post(ROTA, json={"nome": "Verde Oliva"}).json()

    resposta = admin_logado.patch(
        f"/api/v1/admin/produtos/{produto_preto.id}/variacoes",
        json={"variacoes": [{"tipo": "cor", "valor": "escrito errado", "corId": cor["id"]}]},
    )

    assert [v["valor"] for v in resposta.json()] == ["Verde Oliva"]


def teste_mesma_cor_duas_vezes_por_id_responde_400(admin_logado, produto_preto):
    """Textos diferentes, mesmo `corId`: viram a mesma linha depois de
    resolvidos, e a checagem de repetição tem que enxergar isso ANTES do banco."""
    cor = admin_logado.post(ROTA, json={"nome": "Caramelo"}).json()

    resposta = admin_logado.patch(
        f"/api/v1/admin/produtos/{produto_preto.id}/variacoes",
        json={
            "variacoes": [
                {"tipo": "cor", "valor": "um", "corId": cor["id"]},
                {"tipo": "cor", "valor": "outro", "corId": cor["id"]},
            ]
        },
    )

    assert resposta.status_code == 400
    assert resposta.json()["erro"]["codigo"] == "DADOS_INVALIDOS"


def teste_tamanho_com_cor_id_responde_400(admin_logado, produto_preto):
    cor = admin_logado.post(ROTA, json={"nome": "Cinza"}).json()

    resposta = admin_logado.patch(
        f"/api/v1/admin/produtos/{produto_preto.id}/variacoes",
        json={"variacoes": [{"tipo": "tamanho", "valor": "M", "corId": cor["id"]}]},
    )

    assert resposta.status_code == 400


# ======================================================================
# Filtro na vitrine e no painel
# ======================================================================


def teste_filtro_publico_por_cor(sem_sessao, produto_preto):
    resposta = sem_sessao.get("/api/v1/produtos", params={"cor": "preto"})

    assert resposta.status_code == 200
    assert [p["codigo"] for p in resposta.json()["dados"]] == ["CHN-7001"]


def teste_filtro_publico_conta_o_produto_uma_vez_so(sem_sessao, sessao, produto_preto):
    """O produto tem a mesma cor em duas variações (grafias diferentes, como no
    dado anterior à 0007). O EXISTS não pode multiplicar a linha."""
    cor = sessao.scalar(select(Cor).where(Cor.slug == "preto"))
    sessao.add(
        ProdutoVariacao(
            produto_id=produto_preto.id, tipo="cor", valor="preto", cor_id=cor.id, ordem=9
        )
    )
    sessao.commit()

    corpo = sem_sessao.get("/api/v1/produtos", params={"cor": "preto"}).json()

    assert corpo["paginacao"]["total"] == 1
    assert len(corpo["dados"]) == 1


def teste_filtro_publico_com_cor_inexistente_devolve_vazio(sem_sessao, produto_preto):
    corpo = sem_sessao.get("/api/v1/produtos", params={"cor": "nao-existe"}).json()

    assert corpo["dados"] == []
    assert corpo["paginacao"]["total"] == 0


def teste_cor_inativa_nao_filtra(sem_sessao, admin_logado, produto_preto):
    """Cor tirada da paleta não pode ressuscitar por um link antigo."""
    cor = next(c for c in admin_logado.get(ROTA).json() if c["slug"] == "preto")
    admin_logado.patch(f"{ROTA}/{cor['id']}", json={"ativa": False})

    assert sem_sessao.get("/api/v1/produtos", params={"cor": "preto"}).json()["dados"] == []


def teste_paleta_publica_traz_so_as_ativas(sem_sessao, admin_logado, produto_preto):
    admin_logado.post(ROTA, json={"nome": "Bordô", "ativa": False})

    slugs = [c["slug"] for c in sem_sessao.get("/api/v1/cores").json()]

    assert "preto" in slugs
    assert "bordo" not in slugs


def teste_filtro_do_painel_por_cor_id(admin_logado, produto_preto):
    cor = next(c for c in admin_logado.get(ROTA).json() if c["slug"] == "preto")

    corpo = admin_logado.get("/api/v1/admin/produtos", params={"corId": cor["id"]}).json()

    assert [p["codigo"] for p in corpo["dados"]] == ["CHN-7001"]
    assert corpo["paginacao"]["total"] == 1


# ======================================================================
# corId na leitura do painel: a tela reenvia a grade inteira com corId
# ======================================================================


def _grade_do_painel(admin_logado, produto_id):
    return admin_logado.get(f"/api/v1/admin/produtos/{produto_id}").json()["variacoes"]


def _cores_na_paleta(sessao):
    return sessao.scalars(select(Cor.slug).order_by(Cor.slug)).all()


def teste_leitura_do_painel_traz_cor_id_da_variacao(admin_logado, sessao, produto_preto):
    preto = sessao.scalar(select(Cor).where(Cor.slug == "preto"))

    variacoes = {v["tipo"]: v for v in _grade_do_painel(admin_logado, produto_preto.id)}

    assert variacoes["cor"]["corId"] == preto.id
    assert variacoes["tamanho"]["corId"] is None


def teste_resposta_da_gravacao_da_grade_traz_cor_id(admin_logado, sessao, produto_preto):
    preto = sessao.scalar(select(Cor).where(Cor.slug == "preto"))

    resposta = admin_logado.patch(
        f"/api/v1/admin/produtos/{produto_preto.id}/variacoes",
        json={"variacoes": [{"tipo": "cor", "valor": "x", "corId": preto.id}]},
    )

    assert resposta.status_code == 200
    assert resposta.json()[0]["corId"] == preto.id


def teste_regravar_a_grade_depois_de_renomear_nao_duplica_a_cor(admin_logado, sessao, produto_preto):
    """Renomear "Preto" para "Preto Ônix" mantém o slug `preto` e reescreve o
    texto da variação. Pelo caminho de texto, o slug do texto novo
    (`preto-onix`) não existe e a gravação criaria uma cor duplicada. Com o
    `corId` que a leitura devolve, a grade volta intacta."""
    preto = sessao.scalar(select(Cor).where(Cor.slug == "preto"))
    admin_logado.patch(f"{ROTA}/{preto.id}", json={"nome": "Preto Ônix"})
    paleta_antes = _cores_na_paleta(sessao)

    grade = _grade_do_painel(admin_logado, produto_preto.id)
    # Como a tela faz: a grade inteira de volta, e a cor pelo id da paleta.
    reenvio = [
        {"tipo": v["tipo"], "valor": v["valor"], "disponivel": v["disponivel"]}
        | ({"corId": v["corId"]} if v["tipo"] == "cor" else {})
        for v in grade
    ]
    resposta = admin_logado.patch(
        f"/api/v1/admin/produtos/{produto_preto.id}/variacoes", json={"variacoes": reenvio}
    )

    assert resposta.status_code == 200
    assert _cores_na_paleta(sessao) == paleta_antes
    cor = next(v for v in resposta.json() if v["tipo"] == "cor")
    assert (cor["valor"], cor["corId"]) == ("Preto Ônix", preto.id)


def teste_sem_cor_id_a_regravacao_depois_de_renomear_cria_cor_nova(admin_logado, sessao, produto_preto):
    """O risco que o corId evita, registrado: mandar só o texto depois de uma
    renomeação cai no caminho do importador e nasce `preto-onix` na paleta."""
    preto = sessao.scalar(select(Cor).where(Cor.slug == "preto"))
    admin_logado.patch(f"{ROTA}/{preto.id}", json={"nome": "Preto Ônix"})

    admin_logado.patch(
        f"/api/v1/admin/produtos/{produto_preto.id}/variacoes",
        json={"variacoes": [{"tipo": "cor", "valor": "Preto Ônix"}, {"tipo": "tamanho", "valor": "M"}]},
    )

    assert "preto-onix" in _cores_na_paleta(sessao)
