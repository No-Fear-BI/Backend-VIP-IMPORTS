"""Aprovação da fila de revisão do Yupoo (vip_api.rotas.admin_revisao).

O que este arquivo prova: aprovar um álbum cria um PRODUTO DE VERDADE — via
vip_api.servicos.importacao_catalogo.importar_produto, a mesma função de
scripts/importar_catalogo.py — navegável pela API pública, não só uma linha
na tabela paralela de revisão. E que marca/coleção nunca vêm do fornecedor
(`supplier`), só do que o admin escolhe ao aprovar.

Um álbum de teste só, nunca a massa raspada de verdade (13 mil), e a foto
nunca é baixada da rede: `_baixar_foto_yupoo` é trocada por uma imagem em
memória — o teste não depende do Yupoo estar no ar.
"""

import io
import json

import pytest
from PIL import Image
from sqlalchemy import select

from vip_api.configuracao import configuracao
from vip_api.modelos.catalogo import Marca, Produto
from vip_api.modelos.revisao import DecisaoRevisao
from vip_api.rotas import admin_revisao

ROTA = "/api/v1/admin/revisao"

ALBUM_TESTE = {
    "id": "qwer888-999999",
    "name": "Jaqueta bomber preta hoodie",
    "category": "Jaquetas",
    "detail": "Disponibilidade sujeita a confirmação",
    "image": "https://photo.yupoo.com/1234qwer888/abcdef/medium.png",
    "sourceUrl": "https://1234qwer888.x.yupoo.com/albums/999999",
    "supplier": "qwer888",
    "available": True,
}


def _imagem_fake() -> Image.Image:
    return Image.new("RGB", (20, 20), color="red")


@pytest.fixture
def fila_de_teste(tmp_path, monkeypatch):
    """Um álbum só — troca o arquivo que `pendentes`/`decidir` leem e limpa o
    cache do módulo antes e depois, para não vazar entre testes."""
    arquivo = tmp_path / "pending-products.json"
    arquivo.write_text(json.dumps([ALBUM_TESTE]), encoding="utf-8")
    monkeypatch.setattr(admin_revisao, "_arquivo", arquivo)
    admin_revisao._ler_catalogo.cache_clear()
    monkeypatch.setattr(admin_revisao, "_baixar_foto_yupoo", lambda url, source: _imagem_fake())
    monkeypatch.setattr(configuracao, "IMAGENS_DIR", str(tmp_path / "imagens"))
    yield arquivo
    admin_revisao._ler_catalogo.cache_clear()


def teste_pendentes_lista_o_album_de_teste(admin_logado, fila_de_teste):
    resposta = admin_logado.get(f"{ROTA}/pendentes")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["total"] == 1
    assert corpo["items"][0]["id"] == ALBUM_TESTE["id"]
    # supplier aparece na fila interna (admin, protegida) — nunca em rota pública.
    assert corpo["items"][0]["supplier"] == "qwer888"


@pytest.mark.parametrize(('busca', 'esperados'), [
    ('jaquetas', ['qwer888-1', 'qwer888-2']),
    (' JAQUETA  ', ['qwer888-1', 'qwer888-2']),
    ('camisa', ['qwer888-3']),
    ('cintos', ['qwer888-4']),
    ('sueter', ['qwer888-5']),
    ('couro jaquetas', ['qwer888-2']),
    ('165p', ['qwer888-1']),
    ('inexistente', []),
])
def teste_busca_categoria_e_traducao_antes_de_paginar(admin_logado, fila_de_teste, busca, esperados):
    albuns = [dict(ALBUM_TESTE, id=f'qwer888-{i}', category=categoria, name=nome)
              for i, (categoria, nome) in enumerate([
                  ('Jaquetas', '165p SMLXL'), ('Jaquetas', 'leather black'),
                  ('Camisas', '180p'), ('Cintos', '200p'), ('Suéteres', '210p'),
              ], 1)]
    fila_de_teste.write_text(json.dumps(albuns), encoding='utf-8')
    resposta = admin_logado.get(f'{ROTA}/pendentes', params={'busca': busca, 'porPagina': 1})
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo['total'] == len(esperados)
    assert [p['id'] for p in corpo['items']] == esperados[:1]
    if len(esperados) > 1:
        segunda = admin_logado.get(f'{ROTA}/pendentes', params={'busca': busca, 'porPagina': 1, 'pagina': 2}).json()
        assert [p['id'] for p in segunda['items']] == esperados[1:2]
    outro_filtro = admin_logado.get(f'{ROTA}/pendentes', params={'busca': busca, 'categoria': 'Bolsas'}).json()
    assert outro_filtro['total'] == 0


def teste_aprovar_exige_marca_e_colecao(admin_logado, sessao, fila_de_teste):
    resposta = admin_logado.post(ROTA, json={"productId": ALBUM_TESTE["id"], "status": "approved"})

    assert resposta.status_code == 400
    campos = resposta.json()["erro"]["campos"]
    assert "marca" in campos
    assert "colecao" in campos
    assert sessao.scalar(select(Produto).where(Produto.codigo_origem == ALBUM_TESTE["id"])) is None


@pytest.mark.parametrize(('quantidade', 'status'), [(7, 'normal'), (0, 'esgotado'), (None, 'normal')])
def teste_revisao_publica_quantidade_e_disponibilidade(admin_logado, sessao, fila_de_teste, quantidade, status):
    resposta = admin_logado.post(ROTA, json={
        'productId': ALBUM_TESTE['id'], 'status': 'approved',
        'marca': 'Marca Estoque', 'colecao': 'masculino',
        'quantidadeDisponivel': quantidade, 'statusProduto': status,
    })
    assert resposta.status_code == 200
    produto = sessao.scalar(select(Produto).where(Produto.codigo_origem == ALBUM_TESTE['id']))
    assert produto.quantidade_disponivel == quantidade
    assert produto.status == status
    publico = admin_logado.get(f'/api/v1/produtos/{produto.codigo}').json()
    assert publico['quantidadeDisponivel'] == quantidade
    assert publico['status'] == status


@pytest.mark.parametrize('quantidade', [-1, 1.5, True, '3', 2147483648])
def teste_revisao_recusa_quantidade_invalida(admin_logado, sessao, fila_de_teste, quantidade):
    resposta = admin_logado.post(ROTA, json={
        'productId': ALBUM_TESTE['id'], 'status': 'approved',
        'marca': 'Marca Estoque', 'colecao': 'masculino', 'quantidadeDisponivel': quantidade,
    })
    assert resposta.status_code == 400
    assert sessao.scalar(select(Produto).where(Produto.codigo_origem == ALBUM_TESTE['id'])) is None


def teste_aprovar_cria_produto_real_navegavel(admin_logado, sessao, fila_de_teste):
    resposta = admin_logado.post(
        ROTA,
        json={
            "productId": ALBUM_TESTE["id"],
            "status": "approved",
            "translatedName": "Jaqueta bomber",
            "marca": "Nike Teste",
            "colecao": "feminino",
        },
    )
    assert resposta.status_code == 200

    produto = sessao.scalar(select(Produto).where(Produto.codigo_origem == ALBUM_TESTE["id"]))
    assert produto is not None
    assert produto.nome == "Jaqueta bomber"
    assert produto.status == "normal"

    marca = sessao.get(Marca, produto.marca_id)
    assert marca.nome == "Nike Teste"
    # O fornecedor do Yupoo nunca vira marca do produto.
    assert marca.nome != ALBUM_TESTE["supplier"]

    # A imagem foi baixada, redimensionada e salva — não a URL crua do Yupoo,
    # e o nome do fornecedor não vaza nem pelo CAMINHO da imagem pública.
    assert len(produto.imagens) == 1
    assert produto.imagens[0].url.startswith(configuracao.IMAGENS_URL_BASE)
    assert "yupoo" not in produto.imagens[0].url
    assert ALBUM_TESTE["supplier"] not in produto.imagens[0].url

    # codigo_origem/origem_url são rastreabilidade interna — nunca em rota pública.
    publico = admin_logado.get(f"/api/v1/produtos/{produto.codigo}")
    assert publico.status_code == 200
    corpo_publico = publico.json()
    assert "codigoOrigem" not in corpo_publico
    assert "origemUrl" not in corpo_publico
    assert "supplier" not in json.dumps(corpo_publico)
    assert "yupoo" not in json.dumps(corpo_publico).lower()

    # A revisão continua registrando a decisão, e o álbum some da fila.
    decisao = sessao.get(DecisaoRevisao, ALBUM_TESTE["id"])
    assert decisao.status == "approved"
    assert admin_logado.get(f"{ROTA}/pendentes").json()["total"] == 0


def teste_aprovar_de_novo_atualiza_em_vez_de_duplicar(admin_logado, sessao, fila_de_teste):
    corpo = {
        "productId": ALBUM_TESTE["id"],
        "status": "approved",
        "marca": "Nike Teste",
        "colecao": "feminino",
    }
    admin_logado.post(ROTA, json=corpo)
    admin_logado.post(ROTA, json={**corpo, "translatedName": "Jaqueta bomber revisada"})

    produtos = sessao.scalars(
        select(Produto).where(Produto.codigo_origem == ALBUM_TESTE["id"])
    ).all()
    assert len(produtos) == 1
    assert produtos[0].nome == "Jaqueta bomber revisada"


ORIGINAIS = [f"https://photo.yupoo.com/1234qwer888/hash{i}/foto{i}.jpg" for i in range(1, 5)]


def teste_fotos_lista_as_fotos_do_album_com_miniatura(admin_logado, fila_de_teste, monkeypatch):
    monkeypatch.setattr(admin_revisao, "_fotos_do_album", lambda source: ORIGINAIS)

    resposta = admin_logado.get(f"{ROTA}/fotos", params={"produtoId": ALBUM_TESTE["id"]})

    assert resposta.status_code == 200
    fotos = resposta.json()["fotos"]
    assert [f["url"] for f in fotos] == ORIGINAIS
    assert fotos[0]["miniatura"] == "https://photo.yupoo.com/1234qwer888/hash1/medium.jpg"


def teste_fotos_de_produto_inexistente_e_404(admin_logado, fila_de_teste):
    resposta = admin_logado.get(f"{ROTA}/fotos", params={"produtoId": "nao-existe"})

    assert resposta.status_code == 404


def teste_fotos_do_album_le_data_origin_src_com_uid(monkeypatch):
    pedidos = []

    class Resposta:
        def __init__(self, texto):
            self.texto = texto.encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, limite):
            return self.texto

    pagina = (
        '<img data-origin-src="https://photo.yupoo.com/u/a/1.jpg">'
        '<img data-origin-src="//photo.yupoo.com/u/b/2.jpg">'
        '<img data-origin-src="https://photo.yupoo.com/u/a/1.jpg">'
        '<img data-origin-src="https://outro.com/x.jpg">'
    )
    monkeypatch.setattr(admin_revisao, "_albuns", {})
    monkeypatch.setattr(
        admin_revisao, "urlopen", lambda req, timeout: pedidos.append(req.full_url) or Resposta(pagina)
    )

    fotos = admin_revisao._fotos_do_album("https://u.x.yupoo.com/albums/1?referrercate=9")

    assert fotos == ["https://photo.yupoo.com/u/a/1.jpg", "https://photo.yupoo.com/u/b/2.jpg"]
    assert pedidos == ["https://u.x.yupoo.com/albums/1?uid=1"]


def teste_aprovar_com_fotos_escolhidas_usa_a_ordem_e_a_primeira_e_capa(admin_logado, sessao, fila_de_teste, monkeypatch):
    baixadas = []
    monkeypatch.setattr(
        admin_revisao, "_baixar_foto_yupoo", lambda url, source: baixadas.append(url) or _imagem_fake()
    )
    escolhidas = [ORIGINAIS[2], ORIGINAIS[0], ORIGINAIS[3]]

    resposta = admin_logado.post(
        ROTA,
        json={
            "productId": ALBUM_TESTE["id"],
            "status": "approved",
            "marca": "Nike Teste",
            "colecao": "feminino",
            "fotos": escolhidas,
        },
    )

    assert resposta.status_code == 200
    assert baixadas == escolhidas
    produto = sessao.scalar(select(Produto).where(Produto.codigo_origem == ALBUM_TESTE["id"]))
    assert [i.ordem for i in produto.imagens] == [1, 2, 3]
    assert [i.capa for i in produto.imagens] == [True, False, False]
    assert sessao.get(DecisaoRevisao, ALBUM_TESTE["id"]).image == ORIGINAIS[2]


def teste_aprovar_sem_fotos_mantem_so_a_capa_do_album(admin_logado, sessao, fila_de_teste):
    admin_logado.post(
        ROTA,
        json={"productId": ALBUM_TESTE["id"], "status": "approved", "marca": "Nike Teste", "colecao": "feminino"},
    )

    produto = sessao.scalar(select(Produto).where(Produto.codigo_origem == ALBUM_TESTE["id"]))
    assert len(produto.imagens) == 1


def teste_foto_que_falha_nao_cria_produto(admin_logado, sessao, fila_de_teste, monkeypatch):
    def baixar(url, source):
        if url == ORIGINAIS[1]:
            raise admin_revisao.AppError("IMAGEM_INDISPONIVEL", "Imagem indisponível.", 502)
        return _imagem_fake()

    monkeypatch.setattr(admin_revisao, "_baixar_foto_yupoo", baixar)

    resposta = admin_logado.post(
        ROTA,
        json={
            "productId": ALBUM_TESTE["id"],
            "status": "approved",
            "marca": "Nike Teste",
            "colecao": "feminino",
            "fotos": ORIGINAIS[:3],
        },
    )

    assert resposta.status_code == 502
    assert sessao.scalar(select(Produto).where(Produto.codigo_origem == ALBUM_TESTE["id"])) is None
    assert sessao.get(DecisaoRevisao, ALBUM_TESTE["id"]) is None


def teste_publicados_informa_produto_e_estado_das_imagens(admin_logado, fila_de_teste):
    admin_logado.post(
        ROTA,
        json={"productId": ALBUM_TESTE["id"], "status": "approved", "marca": "Nike Teste", "colecao": "feminino"},
    )

    item = admin_logado.get(f"{ROTA}/publicados").json()[0]

    assert item["imagensEstado"] == "concluido"
    assert item["produtoId"]


def teste_rejeitar_nao_cria_produto(admin_logado, sessao, fila_de_teste):
    resposta = admin_logado.post(ROTA, json={"productId": ALBUM_TESTE["id"], "status": "rejected"})

    assert resposta.status_code == 200
    assert sessao.scalar(select(Produto).where(Produto.codigo_origem == ALBUM_TESTE["id"])) is None
    assert admin_logado.get(f"{ROTA}/pendentes").json()["total"] == 0


def teste_rota_produtos_aprovados_publica_nao_existe_mais(sem_sessao):
    """A rota pública /produtos-aprovados vazava fornecedor e URL do Yupoo
    sem exigir sessão — removida: produto aprovado agora é produto de
    verdade, visível pelo catálogo público normal."""
    assert sem_sessao.get("/api/v1/produtos-aprovados").status_code == 404


def _aprovar(admin_logado, **extra):
    return admin_logado.post(
        ROTA,
        json={"productId": ALBUM_TESTE["id"], "status": "approved", "marca": "Nike Teste", "colecao": "feminino", **extra},
    )


def teste_aprovar_sem_preco_funciona_e_fica_vazio(admin_logado, sessao, fila_de_teste):
    assert _aprovar(admin_logado).status_code == 200
    produto = sessao.scalar(select(Produto).where(Produto.codigo_origem == ALBUM_TESTE["id"]))
    assert produto.preco_centavos is None


def teste_aprovar_com_preco_guarda_em_centavos(admin_logado, sessao, fila_de_teste):
    assert _aprovar(admin_logado, precoCentavos=123450).status_code == 200
    produto = sessao.scalar(select(Produto).where(Produto.codigo_origem == ALBUM_TESTE["id"]))
    assert produto.preco_centavos == 123450
    # O painel lê o preço de volta; a rota pública do mesmo produto não.
    assert admin_logado.get(f"/api/v1/admin/produtos/{produto.id}").json()["precoCentavos"] == 123450
    assert "recoCentavos" not in admin_logado.get(f"/api/v1/produtos/{produto.codigo}").text


@pytest.mark.parametrize("invalido", [-1, 10_000_001, "100", True])
def teste_aprovar_com_preco_invalido_da_400_e_nao_cria_produto(admin_logado, sessao, fila_de_teste, invalido):
    resposta = _aprovar(admin_logado, precoCentavos=invalido)
    assert resposta.status_code == 400
    assert sessao.scalar(select(Produto).where(Produto.codigo_origem == ALBUM_TESTE["id"])) is None
    assert sessao.get(DecisaoRevisao, ALBUM_TESTE["id"]) is None
