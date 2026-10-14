"""Saída de GET /atendimento/widget."""

from vip_api.esquemas.base import EsquemaResposta


class WidgetAtendimento(EsquemaResposta):
    """Os dois nulos = chat desligado."""

    widget_url: str | None
    chave_canal: str | None
