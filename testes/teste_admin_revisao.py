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


def teste_aprovar_exige_marca_e_colecao(admin_logado, sessao, fila_de_teste):
    resposta = admin_logado.post(ROTA, json={"productId": ALBUM_TESTE["id"], "status": "approved"})

    assert resposta.status_code == 400
    campos = resposta.json()["erro"]["campos"]
    assert "marca" in campos
    assert "colecao" in campos
    assert sessao.scalar(select(Produto).where(Produto.codigo_origem == ALBUM_TESTE["id"])) is None


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
