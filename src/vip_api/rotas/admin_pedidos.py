"""Pedidos no painel (/admin/pedidos).

O roteador é incluído no grupo protegido de admin_painel.py — sem proteção
própria e sem exceção na varredura.
"""

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from vip_api.banco import obter_sessao
from vip_api.esquemas.pedido import (
    PaginaPedidos,
    PedidoAdmin,
    PedidoStatusEditar,
    StatusPedido,
)
from vip_api.servicos.admin_pedidos import (
    POR_PAGINA_PADRAO,
    atualizar_status,
    listar_pedidos,
)

roteador = APIRouter(prefix="/pedidos", tags=["admin"])


@roteador.get("", response_model=PaginaPedidos)
def pedidos_listar(
    sessao: Session = Depends(obter_sessao),
    status: StatusPedido | None = Query(None, description="Só os pedidos neste status."),
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(POR_PAGINA_PADRAO, alias="porPagina"),
) -> PaginaPedidos:
    """Do mais novo para o mais antigo, com as peças e os dados do cliente de
    cada pedido e a contagem por status (do banco inteiro, para os filtros)."""
    return listar_pedidos(sessao, status, pagina, por_pagina)


@roteador.patch("/{pedidoId}", response_model=PedidoAdmin)
def pedidos_editar(
    corpo: PedidoStatusEditar,
    pedido_id: int = Path(alias="pedidoId"),
    sessao: Session = Depends(obter_sessao),
) -> PedidoAdmin:
    """Só o status muda. Qualquer status vale para qualquer outro (corrigir um
    clique errado, reabrir um pedido)."""
    return atualizar_status(sessao, pedido_id, corpo.status)
