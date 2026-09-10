"""Esquemas da área do cliente."""

from datetime import datetime

from vip_api.esquemas.base import EsquemaEntrada, EsquemaResposta


class IdentificarEntrada(EsquemaEntrada):
    # Só `str`: o formato é validado em `identificar_cliente`, que é onde a
    # normalização acontece — validar em dois lugares com regras diferentes é
    # como um e-mail passa num e é recusado no outro.
    email: str


class ClienteAtualizarEntrada(EsquemaEntrada):
    nome: str | None = None
    telefone: str | None = None


class ClienteEu(EsquemaResposta):
    """Dados do próprio cliente da sessão. `telefone` só aparece aqui e nas
    rotas /admin — nenhuma rota pública devolve telefone de terceiro."""

    id: int
    email: str
    nome: str | None = None
    telefone: str | None = None
    criado_em: datetime


class FavoritoEntrada(EsquemaEntrada):
    produto_id: int
