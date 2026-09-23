"""Cores no importador de planilha (scripts/importar_catalogo.py, revisão 0007).

A coluna `cores` é texto livre do fornecedor. Como marca e categoria, cor que
ainda não existe na paleta é CRIADA, e grafias diferentes da mesma cor caem na
mesma linha de `cores` pelo slug — entre linhas e dentro da mesma célula.
"""

import importlib.util
import sys
from pathlib import Path

import pytest
from sqlalchemy import select

from vip_api.modelos.catalogo import Cor, Produto, ProdutoVariacao

_CAMINHO = Path(__file__).resolve().parents[1] / "scripts" / "importar_catalogo.py"
_spec = importlib.util.spec_from_file_location("importar_catalogo", _CAMINHO)
importar_catalogo = importlib.util.module_from_spec(_spec)
# O script declara @dataclass, que procura o próprio módulo em sys.modules.
sys.modules.setdefault("importar_catalogo", importar_catalogo)
_spec.loader.exec_module(importar_catalogo)


@pytest.fixture
def importar(sessao):
    caches = {"cache_marcas": {}, "cache_colecoes": {}, "cache_categorias": {}, "codigos_vistos": {}}

    def _importar(codigo_origem: str, cores: str) -> Produto:
        linha = {
            "codigo_origem": codigo_origem,
            "nome": f"Peça {codigo_origem}",
            "marca": "Marca Importada",
            "categoria": "Camisas",
            "colecao": "feminino",
            "cores": cores,
        }
        importar_catalogo._importar_linha(
            sessao,
            linha,
            indice=len(caches["codigos_vistos"]) + 2,
            saida_dir=None,
            url_base=None,
            **caches,
        )
        return sessao.scalar(select(Produto).where(Produto.codigo_origem == codigo_origem))

    return _importar


def _cores_do_produto(sessao, produto: Produto) -> list[tuple[str, int]]:
    variacoes = sessao.scalars(
        select(ProdutoVariacao)
        .where(ProdutoVariacao.produto_id == produto.id, ProdutoVariacao.tipo == "cor")
        .order_by(ProdutoVariacao.ordem)
    ).all()
    return [(v.valor, v.cor_id) for v in variacoes]


def teste_cor_nova_na_planilha_e_criada(sessao, importar):
    assert sessao.scalar(select(Cor).where(Cor.slug == "verde-musgo")) is None

    produto = importar("IMP-1", "Verde Musgo")

    cor = sessao.scalar(select(Cor).where(Cor.slug == "verde-musgo"))
    assert cor is not None
    assert cor.nome == "Verde Musgo"
    assert _cores_do_produto(sessao, produto) == [("Verde Musgo", cor.id)]


def teste_grafias_diferentes_em_linhas_diferentes_viram_uma_cor(sessao, importar):
    primeiro = importar("IMP-1", "Verde Musgo")
    segundo = importar("IMP-2", "VERDE musgo")

    cores = sessao.scalars(select(Cor).where(Cor.slug == "verde-musgo")).all()
    assert len(cores) == 1
    # O texto exibido é o nome da paleta, não a grafia desta linha.
    assert _cores_do_produto(sessao, segundo) == _cores_do_produto(sessao, primeiro)


def teste_mesma_cor_repetida_na_celula_nao_derruba_a_linha(sessao, importar):
    produto = importar("IMP-1", "Preto;preto;Azul Petróleo;PRETO")

    preto = sessao.scalar(select(Cor).where(Cor.slug == "preto"))
    azul = sessao.scalar(select(Cor).where(Cor.slug == "azul-petroleo"))
    assert _cores_do_produto(sessao, produto) == [(preto.nome, preto.id), ("Azul Petróleo", azul.id)]
