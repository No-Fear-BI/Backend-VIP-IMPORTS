"""Esquemas do carrinho.

Sem quantidade em lugar nenhum: o mesmo produto com variações diferentes são
dois itens, o mesmo produto com a mesma variação é um item só.
"""

from vip_api.esquemas.base import EsquemaEntrada, EsquemaResposta
from vip_api.esquemas.produto import ProdutoItem, VariacaoDetalhe


class CarrinhoItemSaida(ProdutoItem):
    """Item de listagem + a variação escolhida. `itemId` é o id da LINHA do
    carrinho (o que vai em PATCH/DELETE); `id` continua sendo o do produto."""

    item_id: int
    variacao: VariacaoDetalhe | None = None


class CarrinhoItemEntrada(EsquemaEntrada):
    produto_id: int
    variacao_id: int | None = None


class TrocaVariacaoEntrada(EsquemaEntrada):
    variacao_id: int | None = None


class MigrarEntrada(EsquemaEntrada):
    itens: list[CarrinhoItemEntrada]


class ItemIgnorado(EsquemaResposta):
    produto_id: int
    variacao_id: int | None = None
    motivo: str
    mensagem: str


class MigracaoSaida(EsquemaResposta):
    itens: list[CarrinhoItemSaida]
    ignorados: list[ItemIgnorado]
