"""Esquemas das consultas do painel (tarefas 58 e 60)."""

from datetime import datetime

from pydantic import Field

from vip_api.esquemas.base import EsquemaEntrada, EsquemaResposta


class DestaquesEntrada(EsquemaEntrada):
    """A lista COMPLETA de ids, na ordem em que devem aparecer na home. Lista
    vazia é válida: é como se tira tudo do destaque."""

    ids: list[int] = Field(default_factory=list)


class ContagemPorMarca(EsquemaResposta):
    marca_id: int
    nome: str
    slug: str
    total: int


class Resumo(EsquemaResposta):
    """A tela inicial do painel. Abre a cada login, então o orçamento de
    consultas dela é apertado de propósito."""

    total_produtos: int
    produtos_esgotados: int
    produtos_ocultos: int
    por_marca: list[ContagemPorMarca]
    total_clientes: int


class ClienteAdmin(EsquemaResposta):
    """No painel o telefone APARECE: é a equipe da loja, e é com esse número
    que o atendimento responde a seleção. Nenhuma rota pública devolve
    telefone de terceiro (docs/limitacoes-conhecidas.md)."""

    id: int
    nome: str | None = None
    email: str
    telefone: str | None = None
    ultimo_acesso_em: datetime | None = None
    criado_em: datetime
