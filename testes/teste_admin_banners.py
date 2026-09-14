"""CRUD de banners no painel (tarefa 57).

Duas regras próprias: no máximo quatro ATIVOS (o carrossel contratado no item
2.1 da proposta) e ordem 1..N contígua, como nas imagens do produto.
"""

import pytest

from vip_api.esquemas.admin_catalogo import LIMITE_BANNERS_ATIVOS

ROTA = "/api/v1/admin/banners"


def criar(http, numero: int, ativo: bool = False) -> dict:
    resposta = http.post(
        ROTA,
        json={
            "imagemUrl": f"https://cdn.test/banner{numero}.jpg",
            "titulo": f"Banner {numero}",
            "ativo": ativo,
        },
    )
    assert resposta.status_code == 201
    return resposta.json()


@pytest.fixture
def cinco_banners(admin_logado) -> list[dict]:
    return [criar(admin_logado, numero) for numero in range(1, 6)]


def teste_criar_numera_na_ordem_de_entrada(admin_logado):
    banners = [criar(admin_logado, numero) for numero in range(1, 4)]

    assert [b["ordem"] for b in banners] == [1, 2, 3]
    assert all(b["ativo"] is False for b in banners), "banner nasce como rascunho"


def teste_ativar_ate_quatro_e_recusar_o_quinto(admin_logado, cinco_banners):
    for banner in cinco_banners[:LIMITE_BANNERS_ATIVOS]:
        resposta = admin_logado.patch(f"{ROTA}/{banner['id']}", json={"ativo": True})
        assert resposta.status_code == 200
        assert resposta.json()["ativo"] is True

    quinto = admin_logado.patch(f"{ROTA}/{cinco_banners[4]['id']}", json={"ativo": True})

    assert quinto.status_code == 400
    erro = quinto.json()["erro"]
    assert erro["codigo"] == "DADOS_INVALIDOS"
    assert str(LIMITE_BANNERS_ATIVOS) in erro["mensagem"]
    assert "ativo" in erro["campos"]
    # O quinto continua inativo, e os quatro continuam ativos.
    listagem = admin_logado.get(ROTA).json()
    assert sum(1 for b in listagem if b["ativo"]) == LIMITE_BANNERS_ATIVOS


def teste_criar_ja_ativo_tambem_respeita_o_teto(admin_logado, cinco_banners):
    for banner in cinco_banners[:LIMITE_BANNERS_ATIVOS]:
        admin_logado.patch(f"{ROTA}/{banner['id']}", json={"ativo": True})

    resposta = admin_logado.post(
        ROTA, json={"imagemUrl": "https://cdn.test/novo.jpg", "ativo": True}
    )

    assert resposta.status_code == 400


def teste_desativar_libera_vaga(admin_logado, cinco_banners):
    for banner in cinco_banners[:LIMITE_BANNERS_ATIVOS]:
        admin_logado.patch(f"{ROTA}/{banner['id']}", json={"ativo": True})

    admin_logado.patch(f"{ROTA}/{cinco_banners[0]['id']}", json={"ativo": False})
    resposta = admin_logado.patch(f"{ROTA}/{cinco_banners[4]['id']}", json={"ativo": True})

    assert resposta.status_code == 200


def teste_reativar_quem_ja_esta_ativo_nao_conta_duas_vezes(admin_logado, cinco_banners):
    """Reenviar `ativo: true` num banner que já está ativo não pode ser lido
    como uma quinta ativação — a tela reenvia o formulário inteiro."""
    for banner in cinco_banners[:LIMITE_BANNERS_ATIVOS]:
        admin_logado.patch(f"{ROTA}/{banner['id']}", json={"ativo": True})

    resposta = admin_logado.patch(
        f"{ROTA}/{cinco_banners[0]['id']}", json={"ativo": True, "titulo": "Outro título"}
    )

    assert resposta.status_code == 200
    assert resposta.json()["titulo"] == "Outro título"


def teste_banner_inativo_nao_tem_teto(admin_logado):
    banners = [criar(admin_logado, numero) for numero in range(1, 9)]

    assert len(banners) == 8
    assert [b["ordem"] for b in banners] == list(range(1, 9))


def teste_reordenar_renumera(admin_logado, cinco_banners):
    invertida = [b["id"] for b in reversed(cinco_banners)]

    resposta = admin_logado.patch(f"{ROTA}/ordem", json={"ids": invertida})

    assert resposta.status_code == 200
    assert [b["id"] for b in resposta.json()] == invertida
    assert [b["ordem"] for b in resposta.json()] == [1, 2, 3, 4, 5]


def teste_reordenar_com_lista_parcial_recusa(admin_logado, cinco_banners):
    resposta = admin_logado.patch(
        f"{ROTA}/ordem", json={"ids": [cinco_banners[0]["id"], cinco_banners[1]["id"]]}
    )

    assert resposta.status_code == 400
    assert "ids" in resposta.json()["erro"]["campos"]
    assert [b["ordem"] for b in admin_logado.get(ROTA).json()] == [1, 2, 3, 4, 5]


def teste_excluir_fecha_o_buraco_na_ordem(admin_logado, cinco_banners):
    restantes = admin_logado.delete(f"{ROTA}/{cinco_banners[1]['id']}").json()

    assert [b["ordem"] for b in restantes] == [1, 2, 3, 4]
    assert cinco_banners[1]["id"] not in [b["id"] for b in restantes]


def teste_url_sem_https_recusa(admin_logado):
    resposta = admin_logado.post(ROTA, json={"imagemUrl": "http://cdn.test/x.jpg"})

    assert resposta.status_code == 400


def teste_banner_inexistente_responde_404(admin_logado):
    assert admin_logado.patch(f"{ROTA}/99999", json={"titulo": "X"}).status_code == 404
    assert admin_logado.delete(f"{ROTA}/99999").status_code == 404


def teste_home_mostra_so_os_ativos_na_ordem(admin_logado, sem_sessao, cinco_banners):
    """A ponta pública: o carrossel da home segue a ordem do painel e ignora os
    rascunhos."""
    ativos = [cinco_banners[3], cinco_banners[0], cinco_banners[2]]
    for banner in ativos:
        admin_logado.patch(f"{ROTA}/{banner['id']}", json={"ativo": True})
    admin_logado.patch(f"{ROTA}/ordem", json={"ids": [b["id"] for b in cinco_banners]})

    home = sem_sessao.get("/api/v1/home").json()

    assert [b["id"] for b in home["banners"]] == [
        cinco_banners[0]["id"],
        cinco_banners[2]["id"],
        cinco_banners[3]["id"],
    ]
