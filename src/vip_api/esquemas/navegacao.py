"""Esquemas das rotas de navegação: marcas, coleções e categorias.

`totalProdutos` conta SÓ produto visível. Se "Chanel (43)" abrir uma listagem
com 40 itens porque três estão ocultos, o cliente abre chamado — e tem razão.
"""

from vip_api.esquemas.base import EsquemaResposta
from vip_api.esquemas.produto import Referencia


class MarcaItem(EsquemaResposta):
    id: int
    nome: str
    slug: str
    logo_url: str | None = None
    total_produtos: int


class CorItem(EsquemaResposta):
    """A paleta que a vitrine oferece como filtro (`?cor=`). Só as ativas."""

    id: int
    nome: str
    slug: str
    total_produtos: int


class ColecaoItem(EsquemaResposta):
    id: int
    nome: str
    slug: str


class CategoriaItem(EsquemaResposta):
    id: int
    nome: str
    slug: str
    imagem_url: str | None = None
    total_produtos: int


class CategoriaDestaque(EsquemaResposta):
    """Categoria na home: carrega a coleção junto porque o slug sozinho não
    identifica nada — "bolsas" existe em Feminino e em Masculino, e o link
    precisa dos dois para montar `?colecao=&categoria=`."""

    id: int
    nome: str
    slug: str
    imagem_url: str | None = None
    colecao: Referencia
