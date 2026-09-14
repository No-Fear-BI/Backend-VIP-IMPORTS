"""Esquemas das rotas de produto do painel.

Separados dos esquemas públicos de propósito: aqui `status` aceita e devolve
`oculto` (o painel administra o que o site esconde), e a listagem traz os ids
de marca e categoria, que são o que os seletores do formulário precisam — o
site público usa slug, que é o que vai na URL.
"""

from datetime import datetime
from typing import Literal

from pydantic import ConfigDict, Field
from pydantic.alias_generators import to_camel

from vip_api.esquemas.base import EsquemaEntrada, EsquemaResposta
from vip_api.esquemas.produto import Capa, ImagemDetalhe, Referencia, VariacaoDetalhe

StatusProduto = Literal["normal", "esgotado", "oculto"]

# Teto de ids por chamada em lote. O painel lista 50 por página; 100 cobre
# selecionar duas páginas inteiras e ainda deixa a transação curta. Sem teto,
# uma seleção de "todos" tentaria carregar 11 mil ids numa requisição.
LIMITE_LOTE = 100


class ProdutoAdminItem(EsquemaResposta):
    """Linha da tabela do painel."""

    id: int
    codigo: str
    nome: str
    status: StatusProduto
    destaque: bool
    marca: Referencia
    categoria: Referencia
    colecao: Referencia
    capa: Capa | None = None
    criado_em: datetime
    atualizado_em: datetime


class ProdutoAdminDetalhe(EsquemaResposta):
    """O produto aberto no formulário de edição.

    Traz `marcaId`/`categoriaId` além dos nomes: o formulário precisa do id
    para pré-selecionar o campo, e do nome para exibir sem uma segunda
    chamada.
    """

    id: int
    codigo: str
    nome: str
    descricao: str | None = None
    status: StatusProduto
    destaque: bool
    destaque_ordem: int | None = None
    marca_id: int
    categoria_id: int
    colecao_id: int
    marca: Referencia
    categoria: Referencia
    colecao: Referencia
    imagens: list[ImagemDetalhe]
    variacoes: list[VariacaoDetalhe]
    criado_em: datetime
    atualizado_em: datetime


class ProdutoCriar(EsquemaEntrada):
    # Sem código: o backend gera no padrão da marca. Quem cadastra pelo painel
    # não deveria precisar inventar código nenhum.
    codigo: str | None = Field(None, max_length=32)
    nome: str = Field(min_length=1, max_length=180)
    descricao: str | None = None
    status: StatusProduto = "normal"
    destaque: bool = False
    destaque_ordem: int | None = None
    marca_id: int
    categoria_id: int


class ProdutoEditar(EsquemaEntrada):
    """Todo campo é opcional: o que não vier no corpo não muda. `None` em
    `descricao` e `destaqueOrdem` significa apagar o valor — é por isso que a
    ausência do campo e o `null` precisam ser distinguidos, o que o
    `model_fields_set` do Pydantic resolve."""

    codigo: str | None = Field(None, max_length=32)
    nome: str | None = Field(None, min_length=1, max_length=180)
    descricao: str | None = None
    status: StatusProduto | None = None
    destaque: bool | None = None
    destaque_ordem: int | None = None
    marca_id: int | None = None
    categoria_id: int | None = None


class LoteEntrada(EsquemaEntrada):
    """Os QUATRO campos que a alteração em lote aceita, e nenhum outro.

    `extra="forbid"`: mandar `nome` aqui seria renomear vinte produtos com o
    mesmo texto, e mandar `codigo` seria impossível (é único). O campo a mais
    vira 400 com o nome dele em `erro.campos`, em vez de ser ignorado em
    silêncio — ignorar faria a tela achar que alterou.
    """

    # Mesmo alias camelCase do resto da API, mais o `forbid`.
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="forbid"
    )

    ids: list[int] = Field(min_length=1, max_length=LIMITE_LOTE)
    status: StatusProduto | None = None
    destaque: bool | None = None
    marca_id: int | None = None
    categoria_id: int | None = None


class LoteSaida(EsquemaResposta):
    alterados: int
