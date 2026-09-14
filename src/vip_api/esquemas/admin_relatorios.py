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
    selecoes_no_mes: int
    total_clientes: int


class SelecaoItemAdmin(EsquemaResposta):
    """Item CONGELADO. `produtoId` vem nulo quando o produto foi excluído
    depois do envio — o resto do texto continua igual ao que o cliente viu."""

    produto_id: int | None = None
    codigo: str
    nome: str
    marca: str
    categoria: str
    colecao: str
    imagem_url: str | None = None
    variacao: str | None = None
    observacao: str | None = None


class ClienteDaSelecao(EsquemaResposta):
    id: int | None = None
    nome: str | None = None
    email: str
    telefone: str | None = None


class SelecaoAdmin(EsquemaResposta):
    id: int
    criado_em: datetime
    total_itens: int
    observacao: str | None = None
    cliente: ClienteDaSelecao
    itens: list[SelecaoItemAdmin]


class ClienteAdmin(EsquemaResposta):
    """No painel o telefone APARECE: é a equipe da loja, e é com esse número
    que o atendimento responde a seleção. Nenhuma rota pública devolve
    telefone de terceiro (docs/limitacoes-conhecidas.md)."""

    id: int
    nome: str | None = None
    email: str
    telefone: str | None = None
    total_selecoes: int
    ultimo_acesso_em: datetime | None = None
    criado_em: datetime
