"""Esquemas de marca, categoria e banner no painel (tarefa 57).

Separados dos esquemas públicos de navegação: aqui aparecem `ativa`, `ordem` e
os campos que só o painel edita, e a listagem traz a contagem de produtos —
é o número que a tela precisa mostrar ANTES de alguém tentar excluir.
"""

from datetime import datetime

from pydantic import Field, field_validator

from vip_api.esquemas.base import EsquemaEntrada, EsquemaResposta

# Proposta comercial, item 2.1: "banner principal em carrossel com até 4
# imagens administráveis". O teto vale para os ATIVOS — inativo é rascunho e
# não ocupa espaço no carrossel.
LIMITE_BANNERS_ATIVOS = 4


def _exigir_https(valor: str | None) -> str | None:
    if valor is None:
        return None
    limpo = valor.strip()
    if not limpo:
        return None
    if not limpo.lower().startswith("https://"):
        raise ValueError("A URL precisa começar com https://.")
    return limpo


# ======================================================================
# Marcas
# ======================================================================


class MarcaAdmin(EsquemaResposta):
    id: int
    nome: str
    slug: str
    logo_url: str | None = None
    ordem: int
    ativa: bool
    total_produtos: int
    criado_em: datetime
    atualizado_em: datetime


class MarcaCriar(EsquemaEntrada):
    nome: str = Field(min_length=1, max_length=80)
    # Ausente: o backend gera a partir do nome.
    slug: str | None = Field(None, min_length=1, max_length=80)
    logo_url: str | None = None
    ordem: int = 0
    ativa: bool = True

    _validar_logo = field_validator("logo_url")(_exigir_https)


class MarcaEditar(EsquemaEntrada):
    """`slug` só muda quando vem no corpo — trocar o nome NÃO mexe na URL."""

    nome: str | None = Field(None, min_length=1, max_length=80)
    slug: str | None = Field(None, min_length=1, max_length=80)
    logo_url: str | None = None
    ordem: int | None = None
    ativa: bool | None = None

    _validar_logo = field_validator("logo_url")(_exigir_https)


# ======================================================================
# Cores
# ======================================================================


class CorAdmin(EsquemaResposta):
    """`total_produtos` conta PRODUTOS distintos, não variações: é o número que
    a tela mostra antes de alguém tentar excluir a cor."""

    id: int
    nome: str
    slug: str
    ordem: int
    ativa: bool
    total_produtos: int
    criado_em: datetime
    atualizado_em: datetime


class CorCriar(EsquemaEntrada):
    nome: str = Field(min_length=1, max_length=60)
    # Ausente: o backend gera a partir do nome.
    slug: str | None = Field(None, min_length=1, max_length=60)
    ordem: int = 0
    ativa: bool = True


class CorEditar(EsquemaEntrada):
    """Trocar o nome reescreve o texto exibido nas variações que usam a cor;
    o slug, que é a URL do filtro, só muda quando vem no corpo."""

    nome: str | None = Field(None, min_length=1, max_length=60)
    slug: str | None = Field(None, min_length=1, max_length=60)
    ordem: int | None = None
    ativa: bool | None = None


# ======================================================================
# Categorias
# ======================================================================


class CategoriaAdmin(EsquemaResposta):
    id: int
    colecao_id: int
    colecao_slug: str
    nome: str
    slug: str
    imagem_url: str | None = None
    destaque: bool
    destaque_ordem: int | None = None
    ordem: int
    ativa: bool
    total_produtos: int
    criado_em: datetime
    atualizado_em: datetime


class CategoriaCriar(EsquemaEntrada):
    colecao_id: int
    nome: str = Field(min_length=1, max_length=80)
    slug: str | None = Field(None, min_length=1, max_length=80)
    imagem_url: str | None = None
    destaque: bool = False
    destaque_ordem: int | None = None
    ordem: int = 0
    ativa: bool = True

    _validar_imagem = field_validator("imagem_url")(_exigir_https)


class CategoriaEditar(EsquemaEntrada):
    colecao_id: int | None = None
    nome: str | None = Field(None, min_length=1, max_length=80)
    slug: str | None = Field(None, min_length=1, max_length=80)
    imagem_url: str | None = None
    destaque: bool | None = None
    destaque_ordem: int | None = None
    ordem: int | None = None
    ativa: bool | None = None

    _validar_imagem = field_validator("imagem_url")(_exigir_https)


# ======================================================================
# Banners
# ======================================================================


class BannerAdmin(EsquemaResposta):
    id: int
    titulo: str | None = None
    subtitulo: str | None = None
    imagem_url: str
    imagem_url_mobile: str | None = None
    alt: str | None = None
    link_url: str | None = None
    ordem: int
    ativo: bool
    criado_em: datetime
    atualizado_em: datetime


class BannerCriar(EsquemaEntrada):
    imagem_url: str = Field(min_length=1)
    imagem_url_mobile: str | None = None
    titulo: str | None = Field(None, max_length=120)
    subtitulo: str | None = Field(None, max_length=200)
    alt: str | None = Field(None, max_length=200)
    link_url: str | None = None
    ativo: bool = False

    _validar_imagem = field_validator("imagem_url", "imagem_url_mobile")(_exigir_https)


class BannerEditar(EsquemaEntrada):
    imagem_url: str | None = Field(None, min_length=1)
    imagem_url_mobile: str | None = None
    titulo: str | None = Field(None, max_length=120)
    subtitulo: str | None = Field(None, max_length=200)
    alt: str | None = Field(None, max_length=200)
    link_url: str | None = None
    ativo: bool | None = None

    _validar_imagem = field_validator("imagem_url", "imagem_url_mobile")(_exigir_https)


class OrdemBanners(EsquemaEntrada):
    """A lista COMPLETA de ids na ordem desejada, como nas imagens do produto."""

    ids: list[int] = Field(min_length=1)
