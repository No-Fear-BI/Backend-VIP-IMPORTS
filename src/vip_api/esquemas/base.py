"""Base de todo esquema de SAÍDA da API: atributos em snake_case no Python
(`criado_em`), JSON em camelCase (`criadoEm`) — a conversão é automática via
`alias_generator`, ninguém escreve `Field(alias=...)` na mão. `populate_by_name`
deixa construir a instância tanto por `criado_em=` quanto por `criadoEm=`.

Também mora aqui o envelope genérico de listagem (contrato, seção 1.2) e os
utilitários de cursor de paginação, porque os dois são usados por todo
esquema de listagem do projeto, não por um endpoint específico.
"""

import base64
import binascii
import json
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, model_serializer
from pydantic.alias_generators import to_camel

from vip_api.erros.codigos import CURSOR_INVALIDO
from vip_api.erros.excecoes import AppError


class EsquemaResposta(BaseModel):
    """Todo esquema de saída herda daqui — nunca de `BaseModel` puro."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class EsquemaEntrada(BaseModel):
    """Corpo de requisição. Mesmo alias camelCase da saída — o frontend manda
    `produtoId`, o Python recebe `produto_id`."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


ItemT = TypeVar("ItemT")


class Paginacao(EsquemaResposta):
    total: int
    por_pagina: int
    proximo_cursor: str | None = None
    # Só as listagens do painel usam página numerada (contrato, seção 1.5); as
    # públicas usam cursor. Os dois campos convivem no mesmo envelope, e cada
    # rota preenche o seu — o outro some do JSON.
    pagina: int | None = None

    @model_serializer(mode="wrap")
    def _omitir_o_que_nao_se_aplica(self, handler):
        # "proximoCursor" e "pagina" são opcionais e SOMEM do JSON quando não
        # há valor — não aparecem como null. Isso não dá para expressar só com
        # o tipo do campo, por isso o serializer.
        dados = handler(self)
        for chave in ("proximoCursor", "proximo_cursor", "pagina"):
            if dados.get(chave) is None:
                dados.pop(chave, None)
        return dados


class Pagina(EsquemaResposta, Generic[ItemT]):
    """Envelope de listagem, contrato seção 1.2:
    `{"dados": [...], "paginacao": {"total": ..., "porPagina": ..., "proximoCursor": "..."}}`.
    Parametrize pelo tipo do item: `Pagina[Produto]` — aparece certinho no OpenAPI.
    """

    dados: list[ItemT]
    paginacao: Paginacao


def codificar_cursor(dados: dict) -> str:
    """Codifica o par (campo ordenado, id) — ou o que o endpoint decidir
    colocar ali — em base64 URL-safe, sem padding. Quem monta o dicionário é
    cada endpoint; esta função não sabe nada sobre o que tem dentro dele."""
    bruto = json.dumps(dados, separators=(",", ":"), default=str).encode("utf-8")
    return base64.urlsafe_b64encode(bruto).decode("ascii").rstrip("=")


def decodificar_cursor(cursor: str) -> dict:
    """Inverso de `codificar_cursor`. Cursor malformado nunca chega como 500:
    vira `AppError(CURSOR_INVALIDO)`, que o manipulador de erros converte em
    400 no formato padrão."""
    try:
        preenchimento = "=" * (-len(cursor) % 4)
        bruto = base64.urlsafe_b64decode(cursor + preenchimento)
        return json.loads(bruto)
    except (ValueError, binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AppError(
            codigo=CURSOR_INVALIDO,
            mensagem="O cursor de paginação informado é inválido.",
            status_code=400,
        ) from exc
