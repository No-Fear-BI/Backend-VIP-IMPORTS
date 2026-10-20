"""Pedidos no painel: os dados do cliente e as peças aparecem inteiros, porque é a
equipe da loja que atende o pedido. Nenhuma rota pública devolve nada daqui."""

from datetime import datetime
from typing import Literal

from vip_api.esquemas.base import EsquemaEntrada, EsquemaResposta, Pagina

StatusPedido = Literal["em_andamento", "finalizado", "nao_finalizado"]


class PedidoItemAdmin(EsquemaResposta):
    """Item CONGELADO. `produtoId` vem nulo quando o produto foi excluído depois
    do envio — o resto do texto continua igual ao que o cliente viu."""

    produto_id: int | None = None
    codigo: str
    nome: str
    marca: str
    categoria: str
    colecao: str
    imagem_url: str | None = None
    tamanho: str | None = None
    cor: str | None = None


class ClienteDoPedido(EsquemaResposta):
    """Cópia dos dados do cliente no momento do envio. `id` vem nulo se o
    cadastro foi apagado depois."""

    id: int | None = None
    nome: str | None = None
    email: str
    telefone: str | None = None


class PedidoAdmin(EsquemaResposta):
    id: int
    status: StatusPedido
    criado_em: datetime
    atualizado_em: datetime
    total_itens: int
    cliente: ClienteDoPedido
    itens: list[PedidoItemAdmin]


class ContagemPedidos(EsquemaResposta):
    """Quantos pedidos há em cada status, no banco inteiro (não só na página)."""

    em_andamento: int
    finalizado: int
    nao_finalizado: int
    total: int


class PaginaPedidos(Pagina[PedidoAdmin]):
    """Envelope de sempre, com as contagens por status para os filtros da tela."""

    contagens: ContagemPedidos


class PedidoStatusEditar(EsquemaEntrada):
    status: StatusPedido
