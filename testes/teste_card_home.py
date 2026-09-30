"""Cards de coleção da home (migração 0016): uma categoria no lugar do Feminino (esquerda) ou do
Masculino (direita), com a imagem que o dono escolher. Cada lado tem uma categoria só."""

from testes.fabrica import criar_categoria

CATEGORIAS = "/api/v1/admin/categorias"
HOME = "/api/v1/home"
IMAGEM = "https://exemplo.test/card.jpg"


def _duas(sessao):
    verao = criar_categoria(sessao, "feminino", "Coleção de verão", "colecao-de-verao")
    inverno = criar_categoria(sessao, "feminino", "Coleção de inverno", "colecao-de-inverno")
    sessao.commit()
    return verao, inverno


def _patch(admin_logado, categoria, **corpo):
    resposta = admin_logado.patch(f"{CATEGORIAS}/{categoria.id}", json=corpo)
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def teste_home_sem_card_devolve_lista_vazia(sem_sessao, sessao):
    _duas(sessao)

    assert sem_sessao.get(HOME).json()["cardsColecao"] == []


def teste_categoria_ocupa_o_card_com_a_imagem_escolhida(admin_logado, sem_sessao, sessao):
    verao, _ = _duas(sessao)

    salva = _patch(admin_logado, verao, cardHome="esquerda", cardHomeImagemUrl=IMAGEM)

    assert salva["cardHome"] == "esquerda"
    assert salva["cardHomeImagemUrl"] == IMAGEM
    cards = sem_sessao.get(HOME).json()["cardsColecao"]
    assert cards == [
        {"lado": "esquerda", "id": verao.id, "nome": "Coleção de verão", "slug": "colecao-de-verao", "imagemUrl": IMAGEM}
    ]


def teste_sem_imagem_do_card_vale_a_da_categoria(admin_logado, sem_sessao, sessao):
    verao, _ = _duas(sessao)
    _patch(admin_logado, verao, imagemUrl="https://exemplo.test/categoria.jpg")

    _patch(admin_logado, verao, cardHome="direita")

    card = sem_sessao.get(HOME).json()["cardsColecao"][0]
    assert card["lado"] == "direita"
    assert card["imagemUrl"] == "https://exemplo.test/categoria.jpg"


def teste_cada_lado_tem_uma_categoria_so_e_a_nova_toma_o_lugar(admin_logado, sem_sessao, sessao):
    verao, inverno = _duas(sessao)
    _patch(admin_logado, verao, cardHome="esquerda", cardHomeImagemUrl=IMAGEM)

    _patch(admin_logado, inverno, cardHome="esquerda", cardHomeImagemUrl="https://exemplo.test/outra.jpg")

    cards = sem_sessao.get(HOME).json()["cardsColecao"]
    assert [(c["lado"], c["id"]) for c in cards] == [("esquerda", inverno.id)]
    lista = {c["id"]: c for c in admin_logado.get(CATEGORIAS).json()}
    assert lista[verao.id]["cardHome"] is None
    assert lista[verao.id]["cardHomeImagemUrl"] is None


def teste_dois_lados_ao_mesmo_tempo(admin_logado, sem_sessao, sessao):
    verao, inverno = _duas(sessao)
    _patch(admin_logado, verao, cardHome="esquerda")
    _patch(admin_logado, inverno, cardHome="direita")

    cards = sem_sessao.get(HOME).json()["cardsColecao"]

    assert {c["lado"]: c["id"] for c in cards} == {"esquerda": verao.id, "direita": inverno.id}


def teste_tirar_do_card_apaga_a_imagem_do_card(admin_logado, sem_sessao, sessao):
    verao, _ = _duas(sessao)
    _patch(admin_logado, verao, cardHome="esquerda", cardHomeImagemUrl=IMAGEM)

    salva = _patch(admin_logado, verao, cardHome=None)

    assert salva["cardHome"] is None
    assert salva["cardHomeImagemUrl"] is None
    assert sem_sessao.get(HOME).json()["cardsColecao"] == []


def teste_categoria_escondida_some_do_card_mas_guarda_o_lugar(admin_logado, sem_sessao, sessao):
    verao, _ = _duas(sessao)
    _patch(admin_logado, verao, cardHome="esquerda", cardHomeImagemUrl=IMAGEM)

    _patch(admin_logado, verao, ativa=False)
    assert sem_sessao.get(HOME).json()["cardsColecao"] == []

    _patch(admin_logado, verao, ativa=True)
    assert [c["id"] for c in sem_sessao.get(HOME).json()["cardsColecao"]] == [verao.id]


def teste_criar_categoria_ja_no_card(admin_logado, sem_sessao):
    resposta = admin_logado.post(
        CATEGORIAS, json={"nome": "Verão", "cardHome": "direita", "cardHomeImagemUrl": IMAGEM}
    )

    assert resposta.status_code == 201
    card = sem_sessao.get(HOME).json()["cardsColecao"][0]
    assert (card["lado"], card["nome"], card["imagemUrl"]) == ("direita", "Verão", IMAGEM)


def teste_lado_e_imagem_invalidos_respondem_400(admin_logado, sessao):
    verao, _ = _duas(sessao)

    lado = admin_logado.patch(f"{CATEGORIAS}/{verao.id}", json={"cardHome": "centro"})
    imagem = admin_logado.patch(
        f"{CATEGORIAS}/{verao.id}", json={"cardHome": "esquerda", "cardHomeImagemUrl": "http://inseguro.test/a.jpg"}
    )

    assert lado.status_code == 400
    assert imagem.status_code == 400
    assert "cardHomeImagemUrl" in imagem.json()["erro"]["campos"]


def teste_home_continua_em_quatro_consultas_com_cards(admin_logado, sem_sessao, sessao, contar_consultas):
    verao, inverno = _duas(sessao)
    _patch(admin_logado, verao, cardHome="esquerda", cardHomeImagemUrl=IMAGEM)
    _patch(admin_logado, inverno, cardHome="direita", destaque=True)
    sem_sessao.get(HOME)  # aquece

    with contar_consultas() as consultas:
        sem_sessao.get(HOME)

    assert len(consultas) <= 4


def teste_imagem_enviada_pelo_painel_aceita_http_da_propria_midia(admin_logado, monkeypatch):
    """O upload devolve o endereço de IMAGENS_URL_BASE, que em desenvolvimento é http puro: o
    banner e o card da home precisam aceitá-lo. Qualquer OUTRO http continua recusado."""
    from vip_api.configuracao import configuracao

    monkeypatch.setattr(configuracao, "IMAGENS_URL_BASE", "http://localhost:8000/midia")
    propria = "http://localhost:8000/midia/banners/abc123.webp"

    banner = admin_logado.post("/api/v1/admin/banners", json={"imagemUrl": propria})
    card = admin_logado.post(CATEGORIAS, json={"nome": "Verão", "cardHome": "esquerda", "cardHomeImagemUrl": propria})
    alheia = admin_logado.post("/api/v1/admin/banners", json={"imagemUrl": "http://outro.test/a.jpg"})
    parecida = admin_logado.post("/api/v1/admin/banners", json={"imagemUrl": "http://localhost:8000/midia-falsa/a.jpg"})

    assert banner.status_code == 201, banner.text
    assert card.status_code == 201, card.text
    assert alheia.status_code == 400
    assert parecida.status_code == 400
