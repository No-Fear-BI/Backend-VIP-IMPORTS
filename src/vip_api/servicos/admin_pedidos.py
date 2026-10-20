"""Pedidos no painel: listagem por status e mudança de status pela equipe."""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from vip_api.erros.codigos import PEDIDO_NAO_ENCONTRADO
from vip_api.erros.excecoes import AppError
from vip_api.esquemas.base import Paginacao
from vip_api.esquemas.pedido import (
    ClienteDoPedido,
    ContagemPedidos,
    PaginaPedidos,
    PedidoAdmin,
    PedidoItemAdmin,
)
from vip_api.modelos.pedido import Pedido, PedidoItem

POR_PAGINA_PADRAO = 20
POR_PAGINA_MAXIMO = 100


def _item_admin(item: PedidoItem) -> PedidoItemAdmin:
    return PedidoItemAdmin(
        produto_id=item.produto_id,
        codigo=item.produto_codigo,
        nome=item.produto_nome,
        marca=item.marca_nome,
        categoria=item.categoria_nome,
        colecao=item.colecao_nome,
        imagem_url=item.imagem_url,
        tamanho=item.variacao_tamanho,
        cor=item.variacao_cor,
    )


def _pedido_admin(pedido: Pedido, itens: list[PedidoItem]) -> PedidoAdmin:
    return PedidoAdmin(
        id=pedido.id,
        status=pedido.status,
        criado_em=pedido.criado_em,
        atualizado_em=pedido.atualizado_em,
        total_itens=pedido.total_itens,
        cliente=ClienteDoPedido(
            id=pedido.cliente_id,
            nome=pedido.cliente_nome,
            email=pedido.cliente_email,
            telefone=pedido.cliente_telefone,
        ),
        itens=[_item_admin(i) for i in itens],
    )


def _contagens(sessao: Session) -> ContagemPedidos:
    por_status = dict(
        sessao.execute(select(Pedido.status, func.count()).group_by(Pedido.status)).all()
    )
    em_andamento = por_status.get("em_andamento", 0)
    finalizado = por_status.get("finalizado", 0)
    nao_finalizado = por_status.get("nao_finalizado", 0)
    return ContagemPedidos(
        em_andamento=em_andamento,
        finalizado=finalizado,
        nao_finalizado=nao_finalizado,
        total=em_andamento + finalizado + nao_finalizado,
    )


def listar_pedidos(
    sessao: Session,
    status: str | None = None,
    pagina: int = 1,
    por_pagina: int = POR_PAGINA_PADRAO,
) -> PaginaPedidos:
    por_pagina = max(1, min(por_pagina, POR_PAGINA_MAXIMO))
    pagina = max(1, pagina)

    contagens = _contagens(sessao)
    total = contagens.total if status is None else getattr(contagens, status)

    consulta = select(Pedido)
    if status is not None:
        consulta = consulta.where(Pedido.status == status)
    pedidos = sessao.scalars(
        consulta.order_by(Pedido.criado_em.desc(), Pedido.id.desc())
        .limit(por_pagina)
        .offset((pagina - 1) * por_pagina)
    ).all()

    # As peças de TODOS os pedidos da página numa consulta só — o N+1 aqui seria
    # uma consulta por pedido listado.
    itens_por_pedido: dict[int, list[PedidoItem]] = {p.id: [] for p in pedidos}
    if pedidos:
        for item in sessao.scalars(
            select(PedidoItem)
            .where(PedidoItem.pedido_id.in_(list(itens_por_pedido)))
            .order_by(PedidoItem.pedido_id, PedidoItem.ordem, PedidoItem.id)
        ):
            itens_por_pedido[item.pedido_id].append(item)

    return PaginaPedidos(
        dados=[_pedido_admin(p, itens_por_pedido[p.id]) for p in pedidos],
        paginacao=Paginacao(total=total, por_pagina=por_pagina, pagina=pagina),
        contagens=contagens,
    )


def atualizar_status(sessao: Session, pedido_id: int, status: str) -> PedidoAdmin:
    pedido = sessao.get(Pedido, pedido_id)
    if pedido is None:
        raise AppError(
            codigo=PEDIDO_NAO_ENCONTRADO, mensagem="Pedido não encontrado.", status_code=404
        )
    # Qualquer status vale para qualquer outro: a equipe pode corrigir um clique
    # errado ou reabrir um pedido. Só a data muda quando o status muda de fato.
    if pedido.status != status:
        pedido.status = status
        pedido.atualizado_em = datetime.now(timezone.utc)
        sessao.commit()
    return _pedido_admin(pedido, sorted(pedido.itens, key=lambda i: (i.ordem, i.id)))
