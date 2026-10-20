"""Pedidos no painel: listagem com filtro de pagamento e confirmação do pagamento pela equipe."""

from typing import Literal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from vip_api.erros.codigos import PEDIDO_NAO_ENCONTRADO
from vip_api.erros.excecoes import AppError
from vip_api.esquemas.admin_pedidos import PedidoAdmin
from vip_api.esquemas.base import Pagina, Paginacao
from vip_api.modelos.pedido import Pedido
from vip_api.servicos.admin_relatorios import POR_PAGINA_MAXIMO, POR_PAGINA_PADRAO


def _filtrar(stmt, busca: str | None, situacao: Literal["pago", "pendente"] | None):
    if busca and busca.strip():
        termo = f"%{busca.strip()}%"
        stmt = stmt.where(or_(Pedido.cliente_nome.ilike(termo), Pedido.cliente_email.ilike(termo)))
    if situacao:
        stmt = stmt.where(Pedido.pago.is_(situacao == "pago"))
    return stmt


def listar_pedidos(
    sessao: Session,
    busca: str | None = None,
    situacao: Literal["pago", "pendente"] | None = None,
    pagina: int = 1,
    por_pagina: int = POR_PAGINA_PADRAO,
) -> Pagina[PedidoAdmin]:
    por_pagina = max(1, min(por_pagina, POR_PAGINA_MAXIMO))
    pagina = max(1, pagina)

    total = sessao.scalar(_filtrar(select(func.count()).select_from(Pedido), busca, situacao)) or 0
    pedidos = sessao.scalars(
        _filtrar(select(Pedido), busca, situacao)
        .order_by(Pedido.criado_em.desc(), Pedido.id.desc())
        .limit(por_pagina)
        .offset((pagina - 1) * por_pagina)
    ).all()
    return Pagina[PedidoAdmin](
        dados=[PedidoAdmin.model_validate(p) for p in pedidos],
        paginacao=Paginacao(total=total, por_pagina=por_pagina, pagina=pagina),
    )


def definir_pagamento(sessao: Session, pedido_id: int, pago: bool) -> PedidoAdmin:
    pedido = sessao.get(Pedido, pedido_id)
    if pedido is None:
        raise AppError(codigo=PEDIDO_NAO_ENCONTRADO, mensagem="Pedido não encontrado.", status_code=404)
    pedido.pago = pago
    pedido.pago_em = func.now() if pago else None
    sessao.commit()
    sessao.refresh(pedido)
    return PedidoAdmin.model_validate(pedido)
