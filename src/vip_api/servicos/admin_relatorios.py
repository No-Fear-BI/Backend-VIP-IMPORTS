"""Resumo do catálogo e consultas de clientes, sem histórico de pedidos."""

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from vip_api.esquemas.admin_relatorios import (
    ClienteAdmin,
    ContagemPorMarca,
    Resumo,
)
from vip_api.esquemas.base import Pagina, Paginacao
from vip_api.modelos.catalogo import Marca, Produto
from vip_api.modelos.cliente import Cliente

POR_PAGINA_PADRAO = 20
POR_PAGINA_MAXIMO = 100


# ======================================================================
# Resumo
# ======================================================================


def montar_resumo(sessao: Session) -> Resumo:
    produtos = sessao.execute(
        select(
            func.count().label("total"),
            func.count().filter(Produto.status == "esgotado").label("esgotados"),
            func.count().filter(Produto.status == "oculto").label("ocultos"),
        ).select_from(Produto)
    ).one()

    por_marca = sessao.execute(
        select(Marca.id, Marca.nome, Marca.slug, func.count(Produto.id).label("total"))
        # LEFT JOIN: marca sem produto aparece com zero, que é justamente o
        # número que interessa a quem está limpando o cadastro.
        .outerjoin(Produto, Produto.marca_id == Marca.id)
        .group_by(Marca.id)
        .order_by(func.count(Produto.id).desc(), Marca.nome.asc())
    ).all()

    return Resumo(
        total_produtos=produtos.total,
        produtos_esgotados=produtos.esgotados,
        produtos_ocultos=produtos.ocultos,
        por_marca=[
            ContagemPorMarca(marca_id=l.id, nome=l.nome, slug=l.slug, total=l.total)
            for l in por_marca
        ],
        total_clientes=sessao.scalar(select(func.count()).select_from(Cliente)) or 0,
    )


def _filtrar_clientes(stmt: Select, busca: str | None) -> Select:
    if busca:
        termo = f"%{busca.strip()}%"
        # `email` é citext: o LIKE já ignora caixa sem lower() dos dois lados.
        stmt = stmt.where(or_(Cliente.email.like(termo), Cliente.nome.ilike(termo)))
    return stmt


def listar_clientes(
    sessao: Session,
    busca: str | None = None,
    pagina: int = 1,
    por_pagina: int = POR_PAGINA_PADRAO,
) -> Pagina[ClienteAdmin]:
    por_pagina = max(1, min(por_pagina, POR_PAGINA_MAXIMO))
    pagina = max(1, pagina)

    total = (
        sessao.scalar(_filtrar_clientes(select(func.count()).select_from(Cliente), busca)) or 0
    )

    linhas = sessao.execute(
        _filtrar_clientes(
            select(
                Cliente.id,
                Cliente.nome,
                Cliente.email,
                Cliente.telefone,
                Cliente.ultimo_acesso_em,
                Cliente.criado_em,
            ),
            busca,
        )
        .order_by(Cliente.criado_em.desc(), Cliente.id.desc())
        .limit(por_pagina)
        .offset((pagina - 1) * por_pagina)
    ).all()

    return Pagina[ClienteAdmin](
        dados=[
            ClienteAdmin(
                id=l.id,
                nome=l.nome,
                email=l.email,
                telefone=l.telefone,
                ultimo_acesso_em=l.ultimo_acesso_em,
                criado_em=l.criado_em,
            )
            for l in linhas
        ],
        paginacao=Paginacao(total=total, por_pagina=por_pagina, pagina=pagina),
    )
