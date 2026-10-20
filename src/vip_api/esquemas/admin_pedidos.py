"""Pedidos vistos pelo painel: dados do cliente (cópia do envio), itens e situação do pagamento."""

from datetime import datetime

from vip_api.esquemas.base import EsquemaEntrada, EsquemaResposta
from vip_api.esquemas.selecao import SelecaoItemSaida


class PedidoAdmin(EsquemaResposta):
    id: int
    cliente_nome: str | None = None
    cliente_email: str
    cliente_telefone: str | None = None
    itens: list[SelecaoItemSaida]
    pago: bool
    pago_em: datetime | None = None
    criado_em: datetime


class PedidoPagamentoEntrada(EsquemaEntrada):
    pago: bool
