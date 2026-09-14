"""Consultas do painel: resumo, seleções recebidas e clientes (tarefa 60).

ORÇAMENTO DE CONSULTAS. `GET /admin/resumo` é a primeira tela depois do login
e abre toda vez que alguém entra no painel. O teto é de quatro consultas, e
esta implementação usa TRÊS:

1. os três contadores de produto numa agregação só, com FILTER;
2. a contagem por marca, agrupada — nunca um COUNT por marca dentro de um laço;
3. seleções do mês e total de clientes, as duas como subconsultas escalares do
   mesmo SELECT.

As listagens seguem a mesma disciplina: os itens de TODAS as seleções da página
vêm numa consulta só, e a contagem de seleções por cliente é uma subconsulta
correlacionada sobre as linhas da página — não uma consulta por cliente.
"""

from datetime import datetime, timezone

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from vip_api.erros.codigos import SELECAO_NAO_ENCONTRADA
from vip_api.erros.excecoes import AppError
from vip_api.esquemas.admin_relatorios import (
    ClienteAdmin,
    ClienteDaSelecao,
    ContagemPorMarca,
    Resumo,
    SelecaoAdmin,
    SelecaoItemAdmin,
)
from vip_api.esquemas.base import Pagina, Paginacao
from vip_api.modelos.catalogo import Marca, Produto
from vip_api.modelos.cliente import Cliente
from vip_api.modelos.selecao import Selecao, SelecaoItem
from vip_api.servicos.selecoes import rotulo_variacao

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

    inicio_do_mes = datetime.now(timezone.utc).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    contadores = sessao.execute(
        select(
            select(func.count())
            .select_from(Selecao)
            .where(Selecao.criado_em >= inicio_do_mes)
            .scalar_subquery()
            .label("selecoes_no_mes"),
            select(func.count()).select_from(Cliente).scalar_subquery().label("clientes"),
        )
    ).one()

    return Resumo(
        total_produtos=produtos.total,
        produtos_esgotados=produtos.esgotados,
        produtos_ocultos=produtos.ocultos,
        por_marca=[
            ContagemPorMarca(marca_id=l.id, nome=l.nome, slug=l.slug, total=l.total)
            for l in por_marca
        ],
        selecoes_no_mes=contadores.selecoes_no_mes,
        total_clientes=contadores.clientes,
    )


# ======================================================================
# Seleções recebidas
# ======================================================================


def _itens_por_selecao(sessao: Session, ids: list[int]) -> dict[int, list[SelecaoItemAdmin]]:
    """Os itens de TODAS as seleções da página numa consulta só — o N+1 aqui
    seria uma consulta por seleção listada."""
    agrupados: dict[int, list[SelecaoItemAdmin]] = {identificador: [] for identificador in ids}
    if not ids:
        return agrupados

    for item in sessao.execute(
        select(SelecaoItem)
        .where(SelecaoItem.selecao_id.in_(ids))
        .order_by(SelecaoItem.selecao_id, SelecaoItem.ordem, SelecaoItem.id)
    ).scalars():
        agrupados[item.selecao_id].append(
            SelecaoItemAdmin(
                produto_id=item.produto_id,
                codigo=item.produto_codigo,
                nome=item.produto_nome,
                marca=item.marca_nome,
                categoria=item.categoria_nome,
                colecao=item.colecao_nome,
                imagem_url=item.imagem_url,
                variacao=rotulo_variacao(item.variacao_tamanho, item.variacao_cor),
                observacao=item.observacao,
            )
        )
    return agrupados


def _montar_selecao(selecao: Selecao, itens: list[SelecaoItemAdmin]) -> SelecaoAdmin:
    return SelecaoAdmin(
        id=selecao.id,
        criado_em=selecao.criado_em,
        total_itens=selecao.total_itens,
        observacao=selecao.observacao,
        cliente=ClienteDaSelecao(
            # Tudo congelado na linha da seleção: se o cliente apagar a conta,
            # o atendimento ainda sabe com quem estava falando.
            id=selecao.cliente_id,
            nome=selecao.cliente_nome,
            email=selecao.cliente_email,
            telefone=selecao.cliente_telefone,
        ),
        itens=itens,
    )


def listar_selecoes(
    sessao: Session, pagina: int = 1, por_pagina: int = POR_PAGINA_PADRAO
) -> Pagina[SelecaoAdmin]:
    por_pagina = max(1, min(por_pagina, POR_PAGINA_MAXIMO))
    pagina = max(1, pagina)

    total = sessao.scalar(select(func.count()).select_from(Selecao)) or 0

    selecoes = list(
        sessao.scalars(
            select(Selecao)
            .order_by(Selecao.criado_em.desc(), Selecao.id.desc())
            .limit(por_pagina)
            .offset((pagina - 1) * por_pagina)
        )
    )
    itens = _itens_por_selecao(sessao, [s.id for s in selecoes])

    return Pagina[SelecaoAdmin](
        dados=[_montar_selecao(s, itens[s.id]) for s in selecoes],
        paginacao=Paginacao(total=total, por_pagina=por_pagina, pagina=pagina),
    )


def obter_selecao(sessao: Session, selecao_id: int) -> SelecaoAdmin:
    selecao = sessao.get(Selecao, selecao_id)
    if selecao is None:
        raise AppError(
            codigo=SELECAO_NAO_ENCONTRADA,
            mensagem="Seleção não encontrada.",
            status_code=404,
        )
    return _montar_selecao(selecao, _itens_por_selecao(sessao, [selecao.id])[selecao.id])


# ======================================================================
# Clientes
# ======================================================================


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

    # Subconsulta correlacionada em vez de GROUP BY: o agrupamento rodaria
    # sobre a tabela inteira de seleções antes do LIMIT, e assim ela só roda
    # para as linhas da página — apoiada pelo índice ix_selecoes_cliente.
    contagem = (
        select(func.count())
        .select_from(Selecao)
        .where(Selecao.cliente_id == Cliente.id)
        .scalar_subquery()
        .label("total_selecoes")
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
                contagem,
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
                total_selecoes=l.total_selecoes,
                ultimo_acesso_em=l.ultimo_acesso_em,
                criado_em=l.criado_em,
            )
            for l in linhas
        ],
        paginacao=Paginacao(total=total, por_pagina=por_pagina, pagina=pagina),
    )
