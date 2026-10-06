"""Mensagem e link temporários para abrir o WhatsApp."""

from vip_api.esquemas.base import EsquemaResposta


class SelecaoItemSaida(EsquemaResposta):
    codigo: str
    nome: str
    marca: str
    # Rótulo pronto para exibir, já composto a partir das duas variações
    # selecionadas: "M / Preto", "M", "Preto" ou nulo. É o mesmo texto que vai na
    # mensagem do WhatsApp — a tela não precisa montar nada.
    variacao: str | None = None


class SelecaoSaida(EsquemaResposta):
    """Resposta de `POST /selecoes`."""

    itens: list[SelecaoItemSaida]
    mensagem_whatsapp: str
    link_whatsapp: str
