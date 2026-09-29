"""Listagem pública do catálogo: filtros, busca e paginação por cursor."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import Select, and_, case, func, or_, select, tuple_
from sqlalchemy.orm import Session

from vip_api.erros.codigos import (
    CURSOR_INVALIDO,
    PARAMETRO_OBRIGATORIO,
    PRODUTO_NAO_ENCONTRADO,
)
from vip_api.erros.excecoes import AppError
from vip_api.esquemas.base import (
    Pagina,
    Paginacao,
    codificar_cursor,
    decodificar_cursor,
    exigir_formato_do_cursor,
)
from vip_api.esquemas.produto import (
    Capa,
    ImagemDetalhe,
    ProdutoDetalhe,
    ProdutoItem,
    Referencia,
    VariacaoDetalhe,
)
from vip_api.modelos.catalogo import (
    Categoria,
    Colecao,
    Cor,
    Marca,
    Produto,
    ProdutoImagem,
    ProdutoVariacao,
)
from vip_api.texto import normalizar
from vip_api.servicos.produto_destinos import pertence_categoria, pertence_colecao

POR_PAGINA_PADRAO = 24
POR_PAGINA_MAXIMO = 48

ORDEM_RECENTES = "recentes"
ORDEM_NOME = "nome"

# Regra do cliente (29/09/2026): produto fica NO MÁXIMO 14 dias em Novidades.
# A janela é rolante e calculada na hora da consulta, a partir de `criado_em`:
# sem tarefa agendada e sem coluna nova. Não altera nem apaga nada do produto.
DIAS_NOVIDADE = 14


def _agora() -> datetime:
    """Relógio da janela de novidades. Função à parte para o teste fixá-lo."""
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class FiltrosProduto:
    colecao: str | None = None
    categoria: str | None = None
    marca: str | None = None
    # Slugs de cor separados por vírgula, como `marca`: ?cor=preto,bege é OU
    # entre as duas, e não produto que tenha as duas ao mesmo tempo.
    cor: str | None = None
    busca: str | None = None
    # Só os produtos criados nos últimos DIAS_NOVIDADE dias (página Novidades).
    novidades: bool = False
    ordem: str = ORDEM_RECENTES
    cursor: str | None = None
    por_pagina: int = POR_PAGINA_PADRAO


def _validar_parametros(filtros: FiltrosProduto) -> None:
    # Slug de categoria é único POR COLEÇÃO: "bolsas" existe em Feminino e em
    # Masculino. Sem a coleção junto, não dá para saber de qual se trata.
    if filtros.categoria and not filtros.colecao:
        raise AppError(
            codigo=PARAMETRO_OBRIGATORIO,
            mensagem="Informe a coleção junto com a categoria.",
            status_code=400,
            campos={"colecao": "Obrigatório quando categoria é informada."},
        )


def _ler_cursor(filtros: FiltrosProduto) -> dict | None:
    if not filtros.cursor:
        return None

    dados = exigir_formato_do_cursor(
        decodificar_cursor(filtros.cursor), texto=("o", "v"), inteiros=("id", "t", "n")
    )
    if {"o", "v", "id"} - dados.keys():
        raise AppError(
            codigo=CURSOR_INVALIDO,
            mensagem="O cursor de paginação informado é inválido.",
            status_code=400,
        )
    # Trocar a ordenação no meio da paginação embaralha as chaves e faz item
    # sumir ou repetir. Melhor recusar do que devolver lista furada.
    if dados["o"] != filtros.ordem:
        raise AppError(
            codigo=CURSOR_INVALIDO,
            mensagem="O cursor não corresponde à ordenação informada.",
            status_code=400,
        )
    # O cursor também amarra o recorte de novidades: um cursor de ?novidades=true
    # aplicado a uma consulta sem o filtro (ou o contrário) pularia ou repetiria
    # itens. Cursor antigo, sem `n`, vale como "sem novidades".
    if bool(dados.get("n", 0)) != filtros.novidades:
        raise AppError(
            codigo=CURSOR_INVALIDO,
            mensagem="O cursor não corresponde ao filtro de novidades informado.",
            status_code=400,
        )
    return dados


def _inicio_das_novidades(filtros: FiltrosProduto) -> datetime | None:
    """Início da janela de novidades, ou None sem o filtro. Calculado UMA vez
    por requisição, para a contagem e a página usarem o mesmo corte."""
    if not filtros.novidades:
        return None
    return _agora() - timedelta(days=DIAS_NOVIDADE)


def _resolver_ids(sessao: Session, filtros: FiltrosProduto) -> dict | None:
    """Traduz slugs em ids. Devolve None quando algum slug não existe — o que
    significa filtro que não casa nada, não erro."""
    resolvidos: dict = {
        "colecao_id": None,
        "categoria_id": None,
        "marca_ids": None,
        "cor_ids": None,
        "marcas_da_busca": [],
        "novidades_desde": None,
    }

    if filtros.colecao:
        colecao_id = sessao.scalar(select(Colecao.id).where(Colecao.slug == filtros.colecao))
        if colecao_id is None:
            return None
        resolvidos["colecao_id"] = colecao_id

    if filtros.categoria:
        categoria_id = sessao.scalar(
            select(Categoria.id).where(
                Categoria.slug == filtros.categoria,
                Categoria.colecao_id == resolvidos["colecao_id"],
            )
        )
        if categoria_id is None:
            return None
        resolvidos["categoria_id"] = categoria_id

    if filtros.marca:
        slugs = [s.strip() for s in filtros.marca.split(",") if s.strip()]
        if slugs:
            marca_ids = list(sessao.scalars(select(Marca.id).where(Marca.slug.in_(slugs))))
            if not marca_ids:
                return None
            resolvidos["marca_ids"] = marca_ids

    if filtros.cor:
        slugs = [s.strip() for s in filtros.cor.split(",") if s.strip()]
        if slugs:
            # Cor inativa não entra: o dono tirou da paleta, e um link antigo
            # com ?cor=bordo não pode ressuscitar o filtro na vitrine.
            cor_ids = list(
                sessao.scalars(select(Cor.id).where(Cor.slug.in_(slugs), Cor.ativa.is_(True)))
            )
            if not cor_ids:
                return None
            resolvidos["cor_ids"] = cor_ids

    if filtros.busca:
        # As marcas que casam com o termo são resolvidas ANTES, numa consulta
        # própria (a tabela tem 18 linhas). Sem isso, a condição vira
        # "produtos.nome LIKE ... OR marcas.nome LIKE ...", um OR atravessando
        # duas tabelas — o planejador não consegue usar índice nenhum e cai em
        # Seq Scan na tabela de 11 mil produtos. Com os ids em mãos, o OR fica
        # inteiro dentro de `produtos` e vira BitmapOr de dois índices.
        termo = f"%{normalizar(filtros.busca)}%"
        resolvidos["marcas_da_busca"] = list(
            sessao.scalars(select(Marca.id).where(Marca.nome_busca.like(termo)))
        )

    return resolvidos


def _aplicar_filtros(stmt: Select, filtros: FiltrosProduto, ids: dict) -> Select:
    # Produto oculto some da rota inteira, em qualquer combinação de filtros.
    stmt = stmt.where(Produto.status != "oculto")

    if ids["novidades_desde"] is not None:
        stmt = stmt.where(Produto.criado_em >= ids["novidades_desde"])

    if ids["categoria_id"] is not None:
        # categoria_id já implica a coleção (a FK composta garante), então não
        # precisa filtrar as duas coisas.
        stmt = stmt.where(pertence_categoria(ids["categoria_id"]))
    elif ids["colecao_id"] is not None:
        stmt = stmt.where(pertence_colecao(ids["colecao_id"]))

    if ids["marca_ids"] is not None:
        stmt = stmt.where(Produto.marca_id.in_(ids["marca_ids"]))

    if ids["cor_ids"] is not None:
        # EXISTS, e não JOIN: um produto com três variações da mesma cor
        # apareceria três vezes no JOIN, e consertar isso com DISTINCT quebra
        # o early termination do índice de ordenação (ver _consulta_da_pagina).
        # O EXISTS para na primeira linha que casa, pelo ix_produto_variacoes_cor.
        stmt = stmt.where(
            select(ProdutoVariacao.id)
            .where(
                ProdutoVariacao.produto_id == Produto.id,
                ProdutoVariacao.cor_id.in_(ids["cor_ids"]),
            )
            .exists()
        )

    if filtros.busca:
        termo = f"%{normalizar(filtros.busca)}%"
        # LIKE de substring sobre a coluna já normalizada (minúscula, sem
        # acento) — é o que o índice GIN trigram existente acelera.
        # Nada de similarity(): "bolsa" contra "bolsa clássica acolchoada"
        # fica abaixo do limiar padrão e o cliente acharia que sumiu produto.
        condicoes = [Produto.nome_ordenacao.like(termo)]
        if ids["marcas_da_busca"]:
            condicoes.append(Produto.marca_id.in_(ids["marcas_da_busca"]))
        stmt = stmt.where(or_(*condicoes))

    return stmt


def _aplicar_cursor_e_ordem(stmt: Select, filtros: FiltrosProduto, cursor: dict | None) -> Select:
    if filtros.ordem == ORDEM_NOME:
        # Sem COLLATE aqui: a coluna nome_ordenacao é COLLATE "C" desde a
        # revisão 0003, então ORDER BY e comparação de cursor já usam a mesma
        # ordem do índice por padrão.
        if cursor is not None:
            stmt = stmt.where(
                tuple_(Produto.nome_ordenacao, Produto.id)
                > tuple_(str(cursor["v"]), int(cursor["id"]))
            )
        return stmt.order_by(Produto.nome_ordenacao.asc(), Produto.id.asc())

    if cursor is not None:
        try:
            marca_tempo = datetime.fromisoformat(str(cursor["v"]))
        except ValueError as exc:
            raise AppError(
                codigo=CURSOR_INVALIDO,
                mensagem="O cursor de paginação informado é inválido.",
                status_code=400,
            ) from exc
        # Comparação de TUPLA, não duas condições soltas: é ela que faz o
        # PostgreSQL saltar direto no índice composto e que impede item
        # repetido quando vários produtos têm o mesmo criado_em (a carga da
        # Fatia 5 insere milhares no mesmo segundo).
        stmt = stmt.where(
            tuple_(Produto.criado_em, Produto.id) < tuple_(marca_tempo, int(cursor["id"]))
        )
    return stmt.order_by(Produto.criado_em.desc(), Produto.id.desc())


def _colunas_do_produto():
    return (
        Produto.id,
        Produto.codigo,
        Produto.nome,
        Produto.status,
        Produto.destaque,
        Produto.criado_em,
        Produto.nome_ordenacao,
        Produto.marca_id,
        Produto.categoria_id,
        Produto.colecao_id,
    )


def _envolver_com_juncoes(p) -> Select:
    """Pendura marca, categoria, coleção e capa nas linhas já paginadas."""
    return (
        select(
            p.c.id,
            p.c.codigo,
            p.c.nome,
            p.c.status,
            p.c.destaque,
            p.c.criado_em,
            p.c.nome_ordenacao,
            Marca.nome.label("marca_nome"),
            Marca.slug.label("marca_slug"),
            Categoria.nome.label("categoria_nome"),
            Categoria.slug.label("categoria_slug"),
            Colecao.nome.label("colecao_nome"),
            Colecao.slug.label("colecao_slug"),
            ProdutoImagem.url.label("capa_url"),
            ProdutoImagem.alt.label("capa_alt"),
        )
        .join(Marca, Marca.id == p.c.marca_id)
        .join(Categoria, Categoria.id == p.c.categoria_id)
        .join(Colecao, Colecao.id == p.c.colecao_id)
        # A capa entra pelo índice único parcial uq_produto_imagens_capa;
        # produto sem imagem vem com capa nula, sem placeholder.
        .outerjoin(
            ProdutoImagem,
            and_(ProdutoImagem.produto_id == p.c.id, ProdutoImagem.capa.is_(True)),
        )
    )


def _consulta_da_pagina(filtros: FiltrosProduto, ids: dict, cursor: dict | None, limite: int):
    """Pagina primeiro, junta depois.

    A subconsulta toca só `produtos` — filtros, cursor, ordenação e LIMIT. É
    ela que caminha pelo índice e para nas primeiras `limite` linhas.

    Se os JOINs de marca/categoria/coleção/capa ficassem na mesma camada do
    LIMIT, o planejador perderia o early termination do índice: ele materializa
    as milhares de linhas do filtro, junta todas e só então ordena e corta
    (medido: 14 ms contra 0,05 ms no filtro por coleção). Com a subconsulta,
    os JOINs recebem 25 linhas prontas.
    """
    interna = _aplicar_filtros(select(*_colunas_do_produto()), filtros, ids)
    interna = _aplicar_cursor_e_ordem(interna, filtros, cursor).limit(limite)
    p = interna.subquery("p")

    externa = _envolver_com_juncoes(p)

    # A ordenação precisa ser repetida aqui: o JOIN não preserva a ordem da
    # subconsulta. São 25 linhas, o custo é irrelevante.
    if filtros.ordem == ORDEM_NOME:
        return externa.order_by(p.c.nome_ordenacao.asc(), p.c.id.asc())
    return externa.order_by(p.c.criado_em.desc(), p.c.id.desc())


def _montar_item(linha) -> ProdutoItem:
    return ProdutoItem(
        id=linha.id,
        codigo=linha.codigo,
        nome=linha.nome,
        status=linha.status,
        destaque=linha.destaque,
        marca=Referencia(nome=linha.marca_nome, slug=linha.marca_slug),
        categoria=Referencia(nome=linha.categoria_nome, slug=linha.categoria_slug),
        colecao=Referencia(nome=linha.colecao_nome, slug=linha.colecao_slug),
        capa=Capa(url=linha.capa_url, alt=linha.capa_alt) if linha.capa_url else None,
    )


def _pagina_vazia(por_pagina: int) -> Pagina[ProdutoItem]:
    return Pagina[ProdutoItem](dados=[], paginacao=Paginacao(total=0, por_pagina=por_pagina))


def _buscar_por_codigo_exato(
    sessao: Session, busca: str, por_pagina: int, novidades_desde: datetime | None = None
):
    """Se o termo é um código de produto, devolve aquele produto sozinho.
    É como o atendimento usa o campo quando o cliente manda um código pelo
    WhatsApp — procurar "CHN-0042" e receber 40 resultados parecidos é ruído."""
    interna = (
        select(*_colunas_do_produto())
        .where(Produto.status != "oculto", Produto.codigo == busca.strip().upper())
        .limit(1)
    )
    if novidades_desde is not None:
        interna = interna.where(Produto.criado_em >= novidades_desde)
    linha = sessao.execute(_envolver_com_juncoes(interna.subquery("p"))).first()
    if linha is None:
        return None
    return Pagina[ProdutoItem](
        dados=[_montar_item(linha)], paginacao=Paginacao(total=1, por_pagina=por_pagina)
    )


def listar_produtos(sessao: Session, filtros: FiltrosProduto) -> Pagina[ProdutoItem]:
    _validar_parametros(filtros)

    por_pagina = max(1, min(filtros.por_pagina, POR_PAGINA_MAXIMO))
    cursor = _ler_cursor(filtros)
    novidades_desde = _inicio_das_novidades(filtros)

    if filtros.busca and cursor is None:
        pagina_codigo = _buscar_por_codigo_exato(
            sessao, filtros.busca, por_pagina, novidades_desde
        )
        if pagina_codigo is not None:
            return pagina_codigo

    ids = _resolver_ids(sessao, filtros)
    if ids is None:
        return _pagina_vazia(por_pagina)
    ids["novidades_desde"] = novidades_desde

    # O total é caro e não muda de página para página com os mesmos filtros:
    # conta uma vez na primeira e viaja dentro do cursor. Se o filtro mudar,
    # o cursor deixa de valer e a contagem refaz sozinha.
    if cursor is None:
        contagem = _aplicar_filtros(select(func.count()).select_from(Produto), filtros, ids)
        total = sessao.scalar(contagem) or 0
    else:
        total = int(cursor.get("t", 0))

    # Uma linha a mais só para saber se existe próxima página — sem consulta
    # extra e sem COUNT por página.
    linhas = list(sessao.execute(_consulta_da_pagina(filtros, ids, cursor, por_pagina + 1)))
    tem_proxima = len(linhas) > por_pagina
    linhas = linhas[:por_pagina]

    proximo_cursor = None
    if tem_proxima and linhas:
        ultima = linhas[-1]
        valor = (
            ultima.nome_ordenacao
            if filtros.ordem == ORDEM_NOME
            else ultima.criado_em.isoformat()
        )
        proximo_cursor = codificar_cursor(
            {
                "o": filtros.ordem,
                "v": valor,
                "id": ultima.id,
                "t": total,
                "n": int(filtros.novidades),
            }
        )

    return Pagina[ProdutoItem](
        dados=[_montar_item(linha) for linha in linhas],
        paginacao=Paginacao(total=total, por_pagina=por_pagina, proximo_cursor=proximo_cursor),
    )


def _nao_encontrado() -> AppError:
    return AppError(
        codigo=PRODUTO_NAO_ENCONTRADO,
        mensagem="Produto não encontrado.",
        status_code=404,
    )


def obter_produto(sessao: Session, codigo: str) -> ProdutoDetalhe:
    """`GET /produtos/:codigo`. Produto oculto devolve 404 igual a inexistente:
    oculto some do site, não é "aparece se você souber a URL"."""
    cabecalho = sessao.execute(
        select(
            Produto.id,
            Produto.codigo,
            Produto.nome,
            Produto.descricao,
            Produto.status,
            Produto.destaque,
            Marca.nome.label("marca_nome"),
            Marca.slug.label("marca_slug"),
            Categoria.nome.label("categoria_nome"),
            Categoria.slug.label("categoria_slug"),
            Colecao.nome.label("colecao_nome"),
            Colecao.slug.label("colecao_slug"),
        )
        .join(Marca, Marca.id == Produto.marca_id)
        .join(Categoria, Categoria.id == Produto.categoria_id)
        .join(Colecao, Colecao.id == Produto.colecao_id)
        .where(Produto.codigo == codigo.strip().upper(), Produto.status != "oculto")
    ).first()

    if cabecalho is None:
        raise _nao_encontrado()

    imagens = sessao.execute(
        select(ProdutoImagem.id, ProdutoImagem.url, ProdutoImagem.alt, ProdutoImagem.ordem)
        .where(ProdutoImagem.produto_id == cabecalho.id)
        .order_by(ProdutoImagem.ordem.asc(), ProdutoImagem.id.asc())
    ).all()

    variacoes = sessao.execute(
        select(
            ProdutoVariacao.id,
            ProdutoVariacao.tipo,
            ProdutoVariacao.valor,
            ProdutoVariacao.disponivel,
        )
        .where(ProdutoVariacao.produto_id == cabecalho.id)
        # Agrupadas por tipo: o enum já lista "tamanho" antes de "cor", que é a
        # ordem em que a grade aparece na página.
        .order_by(ProdutoVariacao.tipo.asc(), ProdutoVariacao.ordem.asc(), ProdutoVariacao.id.asc())
    ).all()

    return ProdutoDetalhe(
        id=cabecalho.id,
        codigo=cabecalho.codigo,
        nome=cabecalho.nome,
        descricao=cabecalho.descricao,
        status=cabecalho.status,
        destaque=cabecalho.destaque,
        marca=Referencia(nome=cabecalho.marca_nome, slug=cabecalho.marca_slug),
        categoria=Referencia(nome=cabecalho.categoria_nome, slug=cabecalho.categoria_slug),
        colecao=Referencia(nome=cabecalho.colecao_nome, slug=cabecalho.colecao_slug),
        imagens=[
            ImagemDetalhe(id=i.id, url=i.url, alt=i.alt, ordem=i.ordem) for i in imagens
        ],
        variacoes=[
            VariacaoDetalhe(id=v.id, tipo=v.tipo, valor=v.valor, disponivel=v.disponivel)
            for v in variacoes
        ],
    )


LIMITE_RELACIONADOS = 8


def listar_relacionados(sessao: Session, codigo: str) -> list[ProdutoItem]:
    """Até 8 produtos da mesma marca ou da mesma categoria."""
    origem = sessao.execute(
        select(Produto.id, Produto.marca_id, Produto.categoria_id).where(
            Produto.codigo == codigo.strip().upper(), Produto.status != "oculto"
        )
    ).first()

    if origem is None:
        raise _nao_encontrado()

    # Mesma marca E mesma categoria primeiro, depois só categoria, depois só
    # marca — "bolsa Chanel" puxando outra bolsa Chanel é mais útil que puxar
    # um óculos Chanel qualquer.
    relevancia = case(
        (
            and_(
                Produto.marca_id == origem.marca_id,
                Produto.categoria_id == origem.categoria_id,
            ),
            0,
        ),
        (Produto.categoria_id == origem.categoria_id, 1),
        else_=2,
    ).label("relevancia")

    interna = (
        select(*_colunas_do_produto(), relevancia)
        .where(
            Produto.status != "oculto",
            Produto.id != origem.id,
            or_(
                Produto.marca_id == origem.marca_id,
                Produto.categoria_id == origem.categoria_id,
            ),
        )
        .order_by(relevancia, Produto.criado_em.desc(), Produto.id.desc())
        .limit(LIMITE_RELACIONADOS)
    )
    p = interna.subquery("p")
    linhas = sessao.execute(
        _envolver_com_juncoes(p).order_by(
            p.c.relevancia, p.c.criado_em.desc(), p.c.id.desc()
        )
    ).all()
    return [_montar_item(linha) for linha in linhas]
