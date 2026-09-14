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
    # Rótulo pronto para exibir, já composto a partir das duas variações
    # congeladas: "M / Preto", "M", "Preto" ou nulo. É o mesmo texto que vai na
    # mensagem do WhatsApp — a tela não precisa montar nada.
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
