"""GET /api/v1/burnwood/catalogo — consulta do catálogo pelo agente da Burnwood.

Quem chama é o SERVIDOR da Burnwood, não o navegador: sem sessão, sem portão
de acesso, com `Authorization: Bearer <BURNWOOD_CATALOGO_TOKEN>`. Token errado
ou consulta desligada (token vazio na configuração) = 401.

Só leitura. A resposta é no formato que a Burnwood pediu (`{"items": [...]}`,
campos planos em snake_case, que o agente lê), não no envelope da loja.
"""

import hmac

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from vip_api.banco import obter_sessao
from vip_api.configuracao import configuracao
from vip_api.erros.codigos import NAO_IDENTIFICADO
from vip_api.erros.excecoes import AppError
from vip_api.servicos.burnwood_catalogo import LIMITE_MAXIMO, LIMITE_PADRAO, consultar

roteador = APIRouter(prefix="/burnwood", tags=["burnwood"])


def exigir_token_burnwood(requisicao: Request) -> None:
    esperado = configuracao.BURNWOOD_CATALOGO_TOKEN
    recebido = requisicao.headers.get("Authorization", "")
    # compare_digest: o tempo da comparação não entrega quantos caracteres acertaram.
    if not esperado or not hmac.compare_digest(recebido.encode(), f"Bearer {esperado}".encode()):
        raise AppError(codigo=NAO_IDENTIFICADO, mensagem="Token inválido.", status_code=401)


class ProdutoBurnwood(BaseModel):
    sku: str
    nome: str
    marca: str
    categoria: str
    publico: str
    preco: float | None
    disponivel: bool
    estoque: int | None
    tamanhos: list[str]
    cores: list[str]
    link: str


class CatalogoBurnwood(BaseModel):
    items: list[ProdutoBurnwood]


@roteador.get("/catalogo", response_model=CatalogoBurnwood, dependencies=[Depends(exigir_token_burnwood)])
def catalogo(
    q: str = Query("", max_length=200, description="Poucas palavras da pergunta do cliente."),
    limit: int = Query(LIMITE_PADRAO, ge=1, le=LIMITE_MAXIMO),
    sessao: Session = Depends(obter_sessao),
) -> CatalogoBurnwood:
    return CatalogoBurnwood(items=consultar(sessao, q, limit))
