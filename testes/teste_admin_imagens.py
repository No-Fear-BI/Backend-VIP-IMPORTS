"""Imagens do produto no painel (tarefa 56).

A invariante que todos os testes conferem: ordem 1..N contígua, e a imagem de
ordem 1 é a capa. A capa é o que o visitante vê na grade do site, então
qualquer buraco na numeração vira erro visível na loja.
"""

import pytest
from sqlalchemy import select

from testes.fabrica import criar_categoria, criar_marca, criar_produto
from vip_api.esquemas.admin_midia import LIMITE_IMAGENS
from vip_api.modelos.catalogo import ProdutoImagem

ROTA = "/api/v1/admin/produtos"


@pytest.fixture
def outro_produto(sessao):
    """Segundo produto, para provar que a reordenação não aceita imagem de
    fora."""
    marca = criar_marca(sessao, "Gucci", "gucci")
    categoria = criar_categoria(sessao, "masculino", "Sapatos", "sapatos")
    produto = criar_produto(
        sessao, "GUC-6000", "Sapato Vizinho", marca, categoria, com_imagem=False
    )
    sessao.commit()
    return produto


@pytest.fixture
def produto_sem_imagem(sessao):
    marca = criar_marca(sessao, "Chanel", "chanel")
    categoria = criar_categoria(sessao, "feminino", "Bolsas", "bolsas")
    produto = criar_produto(
        sessao, "CHN-6000", "Bolsa Sem Foto", marca, categoria, com_imagem=False
    )
    sessao.commit()
    return produto


def capa(sessao, produto_id) -> int | None:
    return sessao.scalar(
        select(ProdutoImagem.id).where(
            ProdutoImagem.produto_id == produto_id, ProdutoImagem.capa.is_(True)
        )
    )


def ordens(imagens: list[dict]) -> list[int]:
    return [imagem["ordem"] for imagem in imagens]


def _tres_imagens(http, produto_id) -> list[dict]:
    resposta = http.post(
        f"{ROTA}/{produto_id}/imagens",
        json={
            "imagens": [
                {"url": "https://cdn.test/a.jpg", "alt": "frente"},
                {"url": "https://cdn.test/b.jpg"},
                {"url": "https://cdn.test/c.jpg"},
            ]
        },
    )
    assert resposta.status_code == 201
    return resposta.json()


def teste_acrescentar_numera_e_define_a_capa(admin_logado, sessao, produto_sem_imagem):
    imagens = _tres_imagens(admin_logado, produto_sem_imagem.id)

    assert ordens(imagens) == [1, 2, 3]
    assert [i["url"] for i in imagens] == [
        "https://cdn.test/a.jpg",
        "https://cdn.test/b.jpg",
        "https://cdn.test/c.jpg",
    ]
    assert imagens[0]["alt"] == "frente"
    assert capa(sessao, produto_sem_imagem.id) == imagens[0]["id"]


def teste_novas_entram_no_fim_sem_trocar_a_capa(admin_logado, sessao, produto_sem_imagem):
    primeiras = _tres_imagens(admin_logado, produto_sem_imagem.id)

    resposta = admin_logado.post(
        f"{ROTA}/{produto_sem_imagem.id}/imagens",
        json={"imagens": [{"url": "https://cdn.test/d.jpg"}]},
    )

    assert ordens(resposta.json()) == [1, 2, 3, 4]
    assert resposta.json()[-1]["url"] == "https://cdn.test/d.jpg"
    # Acrescentar foto não muda o que o site mostra na grade.
    assert capa(sessao, produto_sem_imagem.id) == primeiras[0]["id"]


def teste_reordenar_troca_a_capa(admin_logado, sessao, produto_sem_imagem):
    imagens = _tres_imagens(admin_logado, produto_sem_imagem.id)
    invertida = [imagens[2]["id"], imagens[0]["id"], imagens[1]["id"]]

    resposta = admin_logado.patch(
        f"{ROTA}/{produto_sem_imagem.id}/imagens/ordem", json={"ids": invertida}
    )

    assert resposta.status_code == 200
    assert [i["id"] for i in resposta.json()] == invertida
    assert ordens(resposta.json()) == [1, 2, 3]
    assert capa(sessao, produto_sem_imagem.id) == imagens[2]["id"]


def teste_reordenar_com_lista_parcial_recusa(admin_logado, sessao, produto_sem_imagem):
    """Lista parcial reordenaria metade e deixaria a outra metade com a
    numeração antiga — ordem duplicada e capa ambígua."""
    imagens = _tres_imagens(admin_logado, produto_sem_imagem.id)

    resposta = admin_logado.patch(
        f"{ROTA}/{produto_sem_imagem.id}/imagens/ordem",
        json={"ids": [imagens[1]["id"], imagens[0]["id"]]},
    )

    assert resposta.status_code == 400
    assert resposta.json()["erro"]["codigo"] == "DADOS_INVALIDOS"
    assert str(imagens[2]["id"]) in resposta.json()["erro"]["campos"]["ids"]
    # Nada mudou.
    atual = admin_logado.get(f"{ROTA}/{produto_sem_imagem.id}").json()["imagens"]
    assert [i["id"] for i in atual] == [i["id"] for i in imagens]


def teste_reordenar_com_imagem_de_outro_produto_recusa(
    admin_logado, sessao, produto_sem_imagem, outro_produto
):
    imagens = _tres_imagens(admin_logado, produto_sem_imagem.id)
    alheia = _tres_imagens(admin_logado, outro_produto.id)

    resposta = admin_logado.patch(
        f"{ROTA}/{produto_sem_imagem.id}/imagens/ordem",
        json={"ids": [i["id"] for i in imagens] + [alheia[0]["id"]]},
    )

    assert resposta.status_code == 400
    assert str(alheia[0]["id"]) in resposta.json()["erro"]["campos"]["ids"]


def teste_apagar_a_capa_promove_a_seguinte(admin_logado, sessao, produto_sem_imagem):
    imagens = _tres_imagens(admin_logado, produto_sem_imagem.id)

    resposta = admin_logado.delete(f"/api/v1/admin/imagens/{imagens[0]['id']}")

    assert resposta.status_code == 200
    restantes = resposta.json()
    assert [i["id"] for i in restantes] == [imagens[1]["id"], imagens[2]["id"]]
    # Contígua de novo: a que era 2 virou 1, e virou capa.
    assert ordens(restantes) == [1, 2]
    assert capa(sessao, produto_sem_imagem.id) == imagens[1]["id"]


def teste_apagar_do_meio_fecha_o_buraco(admin_logado, sessao, produto_sem_imagem):
    imagens = _tres_imagens(admin_logado, produto_sem_imagem.id)

    restantes = admin_logado.delete(f"/api/v1/admin/imagens/{imagens[1]['id']}").json()

    assert ordens(restantes) == [1, 2]
    assert capa(sessao, produto_sem_imagem.id) == imagens[0]["id"]


def teste_apagar_a_ultima_deixa_o_produto_sem_capa(admin_logado, sessao, produto_sem_imagem):
    (unica,) = admin_logado.post(
        f"{ROTA}/{produto_sem_imagem.id}/imagens",
        json={"imagens": [{"url": "https://cdn.test/unica.jpg"}]},
    ).json()

    resposta = admin_logado.delete(f"/api/v1/admin/imagens/{unica['id']}")

    assert resposta.json() == []
    assert capa(sessao, produto_sem_imagem.id) is None


def teste_url_sem_https_recusa(admin_logado, produto_sem_imagem):
    """Imagem http numa página https é bloqueada pelo navegador como conteúdo
    misto: o produto aparece sem foto e ninguém entende por quê."""
    resposta = admin_logado.post(
        f"{ROTA}/{produto_sem_imagem.id}/imagens",
        json={"imagens": [{"url": "http://cdn.test/a.jpg"}]},
    )

    assert resposta.status_code == 400
    assert resposta.json()["erro"]["codigo"] == "DADOS_INVALIDOS"


def teste_teto_de_imagens_por_produto(admin_logado, produto_sem_imagem):
    _tres_imagens(admin_logado, produto_sem_imagem.id)

    resposta = admin_logado.post(
        f"{ROTA}/{produto_sem_imagem.id}/imagens",
        json={"imagens": [{"url": f"https://cdn.test/{i}.jpg"} for i in range(LIMITE_IMAGENS)]},
    )

    assert resposta.status_code == 400
    assert "imagens" in resposta.json()["erro"]["campos"]


def teste_imagem_inexistente_responde_404(admin_logado):
    assert admin_logado.delete("/api/v1/admin/imagens/999999").status_code == 404


def teste_produto_inexistente_responde_404(admin_logado):
    resposta = admin_logado.post(
        f"{ROTA}/999999/imagens", json={"imagens": [{"url": "https://cdn.test/a.jpg"}]}
    )

    assert resposta.status_code == 404
