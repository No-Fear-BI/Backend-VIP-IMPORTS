"""Esquema da home: uma resposta só com tudo que a página inicial precisa.

Quatro rotas separadas custariam quatro idas e voltas de rede; uma home que
faz oito requisições passa quase um segundo só esperando (tarefa 30 do plano).
"""

from vip_api.esquemas.base import EsquemaResposta
from vip_api.esquemas.navegacao import CategoriaDestaque, MarcaItem
from vip_api.esquemas.produto import ProdutoItem


class BannerItem(EsquemaResposta):
    id: int
    titulo: str | None = None
    subtitulo: str | None = None
    imagem_url: str
    imagem_url_mobile: str | None = None
    alt: str | None = None
    link_url: str | None = None


class Home(EsquemaResposta):
    banners: list[BannerItem]
    destaques: list[ProdutoItem]
    categorias_destaque: list[CategoriaDestaque]
    marcas: list[MarcaItem]
