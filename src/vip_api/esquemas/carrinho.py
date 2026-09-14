"""Esquemas do carrinho.

Sem quantidade em lugar nenhum: o mesmo produto com PARES de variação
diferentes são dois itens, o mesmo produto com o mesmo par é um item só.
"""

from vip_api.esquemas.base import EsquemaEntrada, EsquemaResposta
from vip_api.esquemas.produto import ProdutoItem, VariacaoDetalhe


class CarrinhoItemSaida(ProdutoItem):
    """Item de listagem + as variações escolhidas. `itemId` é o id da LINHA do
    carrinho (o que vai em PATCH/DELETE); `id` continua sendo o do produto.

    Os dois campos de variação vêm separados, e não numa lista, porque a tela
    tem um seletor para cada: assim `variacaoCor` alimenta o seletor de cor sem
    o frontend ter que procurar por `tipo` dentro de um array.
    """

    item_id: int
    variacao_tamanho: VariacaoDetalhe | None = None
    variacao_cor: VariacaoDetalhe | None = None


class CarrinhoItemEntrada(EsquemaEntrada):
    produto_id: int
    variacao_tamanho_id: int | None = None
    variacao_cor_id: int | None = None


class TrocaVariacaoEntrada(EsquemaEntrada):
    """PATCH troca o PAR inteiro: o tipo omitido vira nulo, não fica como
    estava. Mandar sempre os dois seletores é o que a tela já tem em mãos."""

    variacao_tamanho_id: int | None = None
    variacao_cor_id: int | None = None


class MigrarEntrada(EsquemaEntrada):
    itens: list[CarrinhoItemEntrada]


class ItemIgnorado(EsquemaResposta):
    produto_id: int
    variacao_tamanho_id: int | None = None
    variacao_cor_id: int | None = None
    motivo: str
    mensagem: str


class MigracaoSaida(EsquemaResposta):
    itens: list[CarrinhoItemSaida]
    ignorados: list[ItemIgnorado]
