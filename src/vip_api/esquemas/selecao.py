"""Esquemas da seleção enviada.

Tudo aqui é dado CONGELADO: os campos vêm das colunas de texto de
`selecao_itens`, copiadas no envio, não de um JOIN com o catálogo atual.
"""

from datetime import datetime

from vip_api.esquemas.base import EsquemaResposta


class SelecaoItemSaida(EsquemaResposta):
    codigo: str
    nome: str
    marca: str
    variacao: str | None = None


class SelecaoSaida(EsquemaResposta):
    """Resposta de `POST /selecoes`."""

    id: int
    criado_em: datetime
    itens: list[SelecaoItemSaida]
    mensagem_whatsapp: str
    link_whatsapp: str


class SelecaoResumo(EsquemaResposta):
    """Item do histórico em `GET /selecoes`. Sem a mensagem e o link: eles são
    derivados e só fazem sentido no momento do envio."""

    id: int
    criado_em: datetime
    total_itens: int
    itens: list[SelecaoItemSaida]
