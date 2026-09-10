"""Esquemas de saída de produto — formato exato do contrato, seção 02.

Nenhum campo de preço aqui, nem em lugar nenhum do projeto: a loja é catálogo
e o valor é confirmado no atendimento.
"""

from typing import Literal

from vip_api.esquemas.base import EsquemaResposta


class Referencia(EsquemaResposta):
    """`marca`, `categoria` e `colecao` do item: nome exibível + slug de URL."""

    nome: str
    slug: str


class Capa(EsquemaResposta):
    url: str
    alt: str | None = None


class ProdutoItem(EsquemaResposta):
    id: int
    codigo: str
    nome: str
    # A listagem pública nunca devolve "oculto" — produto oculto some da rota
    # inteira. "esgotado" aparece normalmente, marcado: ele é vitrine.
    status: Literal["normal", "esgotado"]
    destaque: bool
    marca: Referencia
    categoria: Referencia
    colecao: Referencia
    # null quando o produto não tem imagem. Sem placeholder — decisão fechada:
    # a tarefa 68 precisa conseguir contar quantos ficaram sem foto.
    capa: Capa | None = None


class ImagemDetalhe(EsquemaResposta):
    id: int
    url: str
    alt: str | None = None
    ordem: int


class VariacaoDetalhe(EsquemaResposta):
    id: int
    tipo: Literal["tamanho", "cor"]
    valor: str
    disponivel: bool


class ProdutoDetalhe(EsquemaResposta):
    """`GET /produtos/:codigo`. Status nunca é "oculto" aqui: produto oculto
    devolve 404, igual a inexistente — some do site, não fica escondido atrás
    de quem souber a URL."""

    id: int
    codigo: str
    nome: str
    descricao: str | None = None
    status: Literal["normal", "esgotado"]
    # A interface `Produto` da seção 07 do contrato declara `destaque` como
    # obrigatório — o detalhe precisa trazer. `capa` continua fora: é
    # redundante com `imagens`, que já vem completo aqui.
    destaque: bool
    marca: Referencia
    categoria: Referencia
    colecao: Referencia
    imagens: list[ImagemDetalhe]
    variacoes: list[VariacaoDetalhe]
