"""Regras de scripts/classificar_fila.py: marca sugerida e categoria pelo título do álbum."""

import importlib.util
from pathlib import Path

import pytest

_caminho = Path(__file__).resolve().parents[1] / "scripts" / "classificar_fila.py"
_spec = importlib.util.spec_from_file_location("classificar_fila", _caminho)
classificar_fila = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(classificar_fila)


@pytest.mark.parametrize(
    ("titulo", "marca"),
    [
        ("73 P GU*CCI 2026 新款", "Gucci"),
        ("65 P L0UIS VUITT0N金丝绒 M-3XL", "Louis Vuitton"),
        ("2024新款L家35-44WW666190", "Louis Vuitton"),
        ("4650 LV", "Louis Vuitton"),
        ("2025新款古家35-42XB067320", "Gucci"),
        ("149P DIO*/迪奥 衬衫", "Dior"),
        ("香奈儿 原单AS6436", "Chanel"),
        ("MARNI男鞋 2026專櫃同步", None),
        ("170 P XS-L", None),
    ],
)
def teste_marca_sugerida(titulo, marca):
    assert classificar_fila.marca_sugerida(titulo) == marca


def teste_apelido_de_outra_marca_nao_vira_louis_vuitton():
    # "AL家" é outra marca; "L家" só vale quando não vem colado a uma letra.
    assert classificar_fila.marca_sugerida("2025新款AL家35-42") is None


def teste_sigla_curta_so_vale_como_palavra_solta():
    assert classificar_fila.marca_sugerida("BOSS2026春夏新款长裤") == "Hugo Boss"
    assert classificar_fila.marca_sugerida("BOSSANOVA 新款") is None
    assert classificar_fila.marca_sugerida("ACNE baggy jeans") is None


@pytest.mark.parametrize(
    ("titulo", "categoria"),
    [
        ("HERMES男士拖鞋 2025專櫃同步", "Chinelos e sapatos baixos"),
        ("L家男士休闲运动鞋 38-45", "Tênis"),
        ("新款拜仁足球运动出场服风衣外套", "Jaquetas esportes"),
        ("85 P 尺寸： 32一件，不退不换，包邮", None),  # "包邮" = frete grátis, não é bolsa
        ("170 P XS-L", None),
    ],
)
def teste_categoria_pelo_titulo(titulo, categoria):
    assert classificar_fila.classificar(titulo) == categoria
