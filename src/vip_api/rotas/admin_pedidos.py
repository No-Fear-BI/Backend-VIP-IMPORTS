"""Pedidos do painel. Incluído no roteador protegido de admin_painel.py."""

from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from vip_api.banco import obter_sessao
from vip_api.esquemas.admin_pedidos import PedidoAdmin, PedidoPagamentoEntrada
from vip_api.esquemas.base import Pagina
from vip_api.servicos.admin_pedidos import definir_pagamento, listar_pedidos
from vip_api.servicos.admin_relatorios import POR_PAGINA_PADRAO

roteador = APIRouter(prefix="/pedidos", tags=["admin"])


@roteador.get("", response_model=Pagina[PedidoAdmin])
def pedidos_listar(
    sessao: Session = Depends(obter_sessao),
    busca: str | None = Query(None, description="Parte do nome ou do e-mail do cliente."),
    situacao: Literal["pago", "pendente"] | None = Query(None),
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(POR_PAGINA_PADRAO, alias="porPagina"),
) -> Pagina[PedidoAdmin]:
    return listar_pedidos(sessao, busca, situacao, pagina, por_pagina)


@roteador.patch("/{pedido_id}", response_model=PedidoAdmin)
def pedido_pagamento(
    pedido_id: int, corpo: PedidoPagamentoEntrada, sessao: Session = Depends(obter_sessao)
) -> PedidoAdmin:
    """Marca o pedido como pago ou volta para pendente."""
    return definir_pagamento(sessao, pedido_id, corpo.pago)
