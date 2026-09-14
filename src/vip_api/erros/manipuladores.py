"""Os três manipuladores de exceção da API. Todo erro que sai pela API tem
exatamente este formato (contrato, seção 1.3):

    { "erro": { "codigo": "...", "mensagem": "...", "campos": { "email": "..." } } }

Regra que não se quebra: nenhum detalhe técnico (nome de tabela, caminho de
arquivo, texto de exceção, traceback) chega no corpo da resposta. A exceção
completa vai para o log, atrás de um identificador curto devolvido no
cabeçalho `X-Rastreio` — não em `erro.campos`, que o frontend renderiza como
mensagem embaixo de um input e onde "rastreio" viraria um erro de campo
inexistente na tela do visitante.
"""

import logging
import uuid

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from vip_api.erros.codigos import DADOS_INVALIDOS, ERRO_INTERNO
from vip_api.erros.excecoes import AppError

logger = logging.getLogger("vip_api.erros")


def _envelope(
    codigo: str,
    mensagem: str,
    campos: dict[str, str] | None = None,
    detalhes: dict | None = None,
) -> dict:
    erro: dict[str, object] = {"codigo": codigo, "mensagem": mensagem}
    if campos:
        erro["campos"] = campos
    if detalhes:
        erro["detalhes"] = detalhes
    return {"erro": erro}


async def tratar_app_error(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=_envelope(exc.codigo, exc.mensagem, exc.campos, exc.detalhes),
    )


# Tradução do "type" bruto do Pydantic v2 para mensagem em português,
# exibível direto ao visitante. Lista curta de propósito — cresce conforme
# aparecer um "type" novo que os esquemas da tarefa 4 em diante realmente usem.
_MENSAGENS_POR_TIPO = {
    "missing": "Este campo é obrigatório.",
    "string_type": "Este campo precisa ser um texto.",
    "string_too_short": "Este campo é muito curto.",
    "string_too_long": "Este campo é muito longo.",
    "int_type": "Este campo precisa ser um número inteiro.",
    "int_parsing": "Este campo precisa ser um número inteiro.",
    "float_type": "Este campo precisa ser um número.",
    "bool_type": "Este campo precisa ser verdadeiro ou falso.",
    "enum": "Valor não permitido para este campo.",
    "greater_than": "Este valor é muito pequeno.",
    "greater_than_equal": "Este valor é muito pequeno.",
    "less_than": "Este valor é muito grande.",
    "less_than_equal": "Este valor é muito grande.",
    "value_error": "Valor inválido para este campo.",
    # Corpo com campo que a rota não aceita (PATCH /admin/produtos/lote):
    # dizer "valor inválido" mandaria procurar erro no valor, e o problema
    # é o campo existir.
    "extra_forbidden": "Este campo não é aceito nesta rota.",
}
_MENSAGEM_PADRAO = "Valor inválido para este campo."


async def tratar_erro_validacao(request: Request, exc: RequestValidationError) -> JSONResponse:
    campos: dict[str, str] = {}
    for erro in exc.errors():
        # erro["loc"] é algo como ("body", "email") ou ("query", "porPagina") —
        # o primeiro elemento é sempre a origem (body/query/path), descartado
        # aqui porque o frontend já sabe onde mandou o campo.
        caminho = [str(parte) for parte in erro["loc"][1:]]
        nome_campo = ".".join(caminho) if caminho else "corpo"
        campos[nome_campo] = _MENSAGENS_POR_TIPO.get(erro["type"], _MENSAGEM_PADRAO)

    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=_envelope(DADOS_INVALIDOS, "Há campos inválidos no envio.", campos),
    )


async def tratar_excecao_nao_tratada(request: Request, exc: Exception) -> JSONResponse:
    id_rastreio = uuid.uuid4().hex[:8]
    logger.exception(
        "Erro não tratado [rastreio=%s] em %s %s", id_rastreio, request.method, request.url.path
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_envelope(ERRO_INTERNO, "Não foi possível concluir a operação."),
        headers={"X-Rastreio": id_rastreio},
    )
