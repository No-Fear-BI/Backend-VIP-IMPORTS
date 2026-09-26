"""CRUD de produto do painel (tarefa 55).

Três coisas separam este serviço do `catalogo.py`, que atende o site:

1. Produto OCULTO aparece. É o painel que administra o que o site esconde —
   uma listagem que some com o oculto deixaria o admin sem como reexibir.
2. Paginação por `pagina`/`porPagina`, não por cursor. A seção 1.5 do contrato
   permite, e OFFSET é honesto aqui: quem administra filtra e vai para a
   página 3, não navega até a 300 como um raspador faria.
3. Escrita passa por objeto ORM, nunca por `update()` do Core quando o nome
   muda: `nome_ordenacao` é preenchida por listener do modelo, e carga pelo
   Core não dispara listener nenhum — o produto entraria com a coluna de
   ordenação vazia e sumiria da ordenação por nome do site.
"""

import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import and_, case, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from vip_api.erros.codigos import (
    CODIGO_EM_USO,
    DADOS_INVALIDOS,
    PRODUTO_NAO_ENCONTRADO,
)
from vip_api.erros.excecoes import AppError
from vip_api.esquemas.admin_produto import (
    ProdutoAdminDetalhe,
    ProdutoAdminItem,
    ProdutoCriar,
    ProdutoEditar,
    VariacaoAdmin,
)
from vip_api.esquemas.base import Pagina, Paginacao
from vip_api.esquemas.produto import Capa, ImagemDetalhe, Referencia
from vip_api.modelos.catalogo import (
    Categoria,
    Colecao,
    Marca,
    Produto,
    ProdutoImagem,
    ProdutoVariacao,
)
from vip_api.modelos.produto_destinos import ProdutoCategoriaAdicional
from vip_api.servicos.produto_destinos import definir_destinos, validar_destinos
from vip_api.servicos.admin_variacoes import remover_variacoes
from vip_api.texto import normalizar

POR_PAGINA_PADRAO = 50
POR_PAGINA_MAXIMO = 100

SUFIXO_COPIA = " (cópia)"
# Quantas vezes tentar o próximo sequencial quando o INSERT bate no UNIQUE.
# São duas contas no painel: a colisão é rara, e 20 tentativas cobrem até uma
# carga automatizada disputando a mesma marca.
TENTATIVAS_DE_CODIGO = 20


@dataclass(frozen=True)
class FiltrosAdmin:
    busca: str | None = None
    marca_id: int | None = None
    categoria_id: int | None = None
    colecao_id: int | None = None
    # Id, e não slug como na vitrine: o painel já tem a lista de cores em mãos
    # (GET /admin/cores) e trabalha com id em todos os outros filtros.
    cor_id: int | None = None
    status: str | None = None
    pagina: int = 1
    por_pagina: int = POR_PAGINA_PADRAO


# ======================================================================
# Leitura
# ======================================================================


def _aplicar_filtros(stmt, filtros: FiltrosAdmin):
    # Nenhum `status != 'oculto'` aqui: é a diferença que define esta rota.
    if filtros.status:
        stmt = stmt.where(Produto.status == filtros.status)
    if filtros.marca_id is not None:
        stmt = stmt.where(Produto.marca_id == filtros.marca_id)
    if filtros.categoria_id is not None:
        from vip_api.servicos.produto_destinos import pertence_categoria
        stmt = stmt.where(pertence_categoria(filtros.categoria_id))
    elif filtros.colecao_id is not None:
        from vip_api.servicos.produto_destinos import pertence_colecao
        stmt = stmt.where(pertence_colecao(filtros.colecao_id))

    if filtros.cor_id is not None:
        # EXISTS pelo mesmo motivo da vitrine: JOIN repetiria o produto que tem
        # a cor em mais de uma variação, e o total da paginação mentiria.
        stmt = stmt.where(
            select(ProdutoVariacao.id)
            .where(
                ProdutoVariacao.produto_id == Produto.id,
                ProdutoVariacao.cor_id == filtros.cor_id,
            )
            .exists()
        )

    if filtros.busca:
        termo = f"%{normalizar(filtros.busca)}%"
        # Nome normalizado OU código. O código entra em maiúsculas porque é
        # assim que está gravado — quem digita "chn-0042" na busca do painel
        # está procurando CHN-0042.
        stmt = stmt.where(
            or_(
                Produto.nome_ordenacao.like(termo),
                Produto.codigo.like(f"%{filtros.busca.strip().upper()}%"),
            )
        )
    return stmt


def listar_produtos(sessao: Session, filtros: FiltrosAdmin) -> Pagina[ProdutoAdminItem]:
    por_pagina = max(1, min(filtros.por_pagina, POR_PAGINA_MAXIMO))
    pagina = max(1, filtros.pagina)

    total = (
        sessao.scalar(
            _aplicar_filtros(select(func.count()).select_from(Produto), filtros)
        )
        or 0
    )

    # Mesma estratégia do catálogo público: pagina primeiro numa subconsulta
    # que só toca `produtos`, junta depois. Com o JOIN na mesma camada do
    # LIMIT/OFFSET o planejador materializa o filtro inteiro antes de cortar.
    interna = (
        _aplicar_filtros(
            select(
                Produto.id,
                Produto.codigo,
                Produto.nome,
                Produto.status,
                Produto.destaque,
                Produto.criado_em,
                Produto.atualizado_em,
                Produto.marca_id,
                Produto.categoria_id,
                Produto.colecao_id,
            ),
            filtros,
        )
        .order_by(Produto.criado_em.desc(), Produto.id.desc())
        .limit(por_pagina)
        .offset((pagina - 1) * por_pagina)
    ).subquery("p")

    linhas = sessao.execute(
        select(
            interna.c.id,
            interna.c.codigo,
            interna.c.nome,
            interna.c.status,
            interna.c.destaque,
            interna.c.criado_em,
            interna.c.atualizado_em,
            Marca.nome.label("marca_nome"),
            Marca.slug.label("marca_slug"),
            Categoria.nome.label("categoria_nome"),
            Categoria.slug.label("categoria_slug"),
            Colecao.nome.label("colecao_nome"),
            Colecao.slug.label("colecao_slug"),
            ProdutoImagem.url.label("capa_url"),
            ProdutoImagem.alt.label("capa_alt"),
        )
        .join(Marca, Marca.id == interna.c.marca_id)
        .join(Categoria, Categoria.id == interna.c.categoria_id)
        .join(Colecao, Colecao.id == interna.c.colecao_id)
        .outerjoin(
            ProdutoImagem,
            and_(ProdutoImagem.produto_id == interna.c.id, ProdutoImagem.capa.is_(True)),
        )
        .order_by(interna.c.criado_em.desc(), interna.c.id.desc())
    ).all()

    return Pagina[ProdutoAdminItem](
        dados=[
            ProdutoAdminItem(
                id=linha.id,
                codigo=linha.codigo,
                nome=linha.nome,
                status=linha.status,
                destaque=linha.destaque,
                marca=Referencia(nome=linha.marca_nome, slug=linha.marca_slug),
                categoria=Referencia(nome=linha.categoria_nome, slug=linha.categoria_slug),
                colecao=Referencia(nome=linha.colecao_nome, slug=linha.colecao_slug),
                capa=Capa(url=linha.capa_url, alt=linha.capa_alt) if linha.capa_url else None,
                criado_em=linha.criado_em,
                atualizado_em=linha.atualizado_em,
            )
            for linha in linhas
        ],
        paginacao=Paginacao(total=total, por_pagina=por_pagina, pagina=pagina),
    )


def _nao_encontrado() -> AppError:
    return AppError(
        codigo=PRODUTO_NAO_ENCONTRADO, mensagem="Produto não encontrado.", status_code=404
    )


def _carregar(sessao: Session, produto_id: int) -> Produto:
    produto = sessao.get(Produto, produto_id)
    if produto is None:
        raise _nao_encontrado()
    return produto


def obter_produto(sessao: Session, produto_id: int) -> ProdutoAdminDetalhe:
    """Por ID, não por código: no painel o código é editável, e buscar o
    registro pela chave que o formulário está editando é como a tela perde o
    produto no meio da edição."""
    cabecalho = sessao.execute(
        select(
            Produto,
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
        .where(Produto.id == produto_id)
    ).first()

    if cabecalho is None:
        raise _nao_encontrado()

    produto = cabecalho[0]
    imagens = sessao.execute(
        select(ProdutoImagem.id, ProdutoImagem.url, ProdutoImagem.alt, ProdutoImagem.ordem)
        .where(ProdutoImagem.produto_id == produto.id)
        .order_by(ProdutoImagem.ordem.asc(), ProdutoImagem.id.asc())
    ).all()
    variacoes = sessao.execute(
        select(
            ProdutoVariacao.id,
            ProdutoVariacao.tipo,
            ProdutoVariacao.valor,
            ProdutoVariacao.disponivel,
            ProdutoVariacao.cor_id,
        )
        .where(ProdutoVariacao.produto_id == produto.id)
        .order_by(ProdutoVariacao.tipo.asc(), ProdutoVariacao.ordem.asc(), ProdutoVariacao.id.asc())
    ).all()
    categorias_ids = [produto.categoria_id] + list(sessao.scalars(select(ProdutoCategoriaAdicional.categoria_id).where(ProdutoCategoriaAdicional.produto_id == produto.id)))

    return ProdutoAdminDetalhe(
        id=produto.id,
        codigo=produto.codigo,
        nome=produto.nome,
        descricao=produto.descricao,
        status=produto.status,
        destaque=produto.destaque,
        destaque_ordem=produto.destaque_ordem,
        marca_id=produto.marca_id,
        categoria_id=produto.categoria_id,
        colecao_id=produto.colecao_id,
        marca=Referencia(nome=cabecalho.marca_nome, slug=cabecalho.marca_slug),
        categoria=Referencia(nome=cabecalho.categoria_nome, slug=cabecalho.categoria_slug),
        colecao=Referencia(nome=cabecalho.colecao_nome, slug=cabecalho.colecao_slug),
        categorias_ids=categorias_ids,
        imagens=[ImagemDetalhe(id=i.id, url=i.url, alt=i.alt, ordem=i.ordem) for i in imagens],
        variacoes=[
            VariacaoAdmin(
                id=v.id, tipo=v.tipo, valor=v.valor, disponivel=v.disponivel, cor_id=v.cor_id
            )
            for v in variacoes
        ],
        criado_em=produto.criado_em,
        atualizado_em=produto.atualizado_em,
    )


# ======================================================================
# Código gerado (tarefa 71)
# ======================================================================


def _prefixo_da_marca(sessao: Session, marca_id: int) -> str:
    """Três letras para o código. O prefixo JÁ USADO pela marca vale mais que
    qualquer regra derivada do nome: o catálogo real tem GUC para Gucci e CHN
    para Chanel, e gerar "GCC" agora deixaria a mesma marca com dois padrões
    de código convivendo na mesma tela."""
    # A MESMA expressão no SELECT e no GROUP BY, reaproveitando o objeto:
    # chamar func.split_part() duas vezes gera dois conjuntos de parâmetros e
    # o PostgreSQL não reconhece os dois como a mesma coisa.
    prefixo = func.split_part(Produto.codigo, "-", 1).label("prefixo")
    # DESEMPATE quando a marca já usa mais de um prefixo na base: vence o
    # MAIS FREQUENTE, e o `id` desempata o empate para a escolha não mudar de
    # uma chamada para outra. Isso deixa de ser hipótese depois da carga da
    # Fatia 5, em que uma marca pode chegar com códigos de duas origens.
    usado = sessao.scalar(
        select(prefixo)
        .where(Produto.marca_id == marca_id, Produto.codigo.like("%-%"))
        .group_by(prefixo)
        .order_by(func.count().desc(), func.min(Produto.id).asc())
        .limit(1)
    )
    if usado and len(usado) == 3 and usado.isalpha():
        return usado.upper()

    return _prefixo_do_nome(sessao.get(Marca, marca_id).nome)


def _prefixo_do_nome(nome: str) -> str:
    """Marca nova, sem produto nenhum: deriva do nome. Uma palavra vira a
    inicial mais as duas consoantes seguintes (Chanel -> CHN); duas ou mais
    viram as iniciais (Louis Vuitton -> LVT). É só um rótulo legível — quem
    garante unicidade é o UNIQUE do banco."""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", nome) if not unicodedata.combining(c)
    )
    palavras = [p for p in "".join(c if c.isalpha() else " " for c in sem_acento).split() if p]
    if not palavras:
        return "PRD"

    if len(palavras) >= 2:
        letras = "".join(p[0] for p in palavras)[:3]
    else:
        palavra = palavras[0]
        consoantes = [c for c in palavra[1:] if c.lower() not in "aeiou"]
        letras = (palavra[0] + "".join(consoantes))[:3]

    letras = letras.upper()
    # Marca curta demais ("Y-3" viraria "Y"): completa com o próprio nome.
    return (letras + palavras[0].upper() + "XXX")[:3]


def _proximo_sequencial(sessao: Session, prefixo: str) -> int:
    maior = sessao.scalar(
        select(func.max(func.substring(Produto.codigo, len(prefixo) + 2)))
        .where(Produto.codigo.like(f"{prefixo}-%"))
    )
    try:
        return int(maior) + 1
    except (TypeError, ValueError):
        return 1


def _e_colisao_de_codigo(erro: IntegrityError) -> bool:
    return "uq_produtos_codigo" in str(getattr(erro, "orig", erro))


def _gravar_com_codigo_gerado(sessao: Session, produto: Produto, prefixo: str) -> Produto:
    """Insere tentando o próximo sequencial até o banco aceitar.

    "Pega o maior e soma um" é correto até duas pessoas salvarem no mesmo
    segundo: as duas leem o mesmo maior, e a segunda estoura no UNIQUE com um
    500 na cara de quem estava cadastrando. Aqui a colisão é esperada, e a
    resposta a ela é tentar o próximo — dentro de um SAVEPOINT, para a
    transação continuar utilizável depois do erro.
    """
    sequencial = _proximo_sequencial(sessao, prefixo)

    for tentativa in range(TENTATIVAS_DE_CODIGO):
        produto.codigo = f"{prefixo}-{sequencial + tentativa:04d}"
        try:
            with sessao.begin_nested():
                sessao.add(produto)
                sessao.flush()
        except IntegrityError as erro:
            # Só a colisão de código é esperada. Qualquer outra violação (FK de
            # marca, CHECK de destaque) subiria mascarada como "não consegui
            # gerar código", e mandaria o admin procurar o problema errado.
            if not _e_colisao_de_codigo(erro):
                raise
            continue
        sessao.commit()
        return produto

    raise AppError(
        codigo=CODIGO_EM_USO,
        mensagem="Não foi possível gerar um código para este produto. Informe um manualmente.",
        status_code=409,
        campos={"codigo": "Informe um código manualmente."},
    )


# ======================================================================
# Escrita
# ======================================================================


def _codigo_em_uso(codigo: str) -> AppError:
    return AppError(
        codigo=CODIGO_EM_USO,
        mensagem=f"O código {codigo} já está em uso por outro produto.",
        status_code=409,
        campos={"codigo": "Este código já está em uso."},
    )


def _campo_invalido(campo: str, mensagem: str) -> AppError:
    return AppError(
        codigo=DADOS_INVALIDOS,
        mensagem="Há campos inválidos no envio.",
        status_code=400,
        campos={campo: mensagem},
    )


def _conferir_marca(sessao: Session, marca_id: int) -> None:
    if sessao.get(Marca, marca_id) is None:
        raise _campo_invalido("marcaId", "Marca não encontrada.")


def _colecao_da_categoria(sessao: Session, categoria_id: int) -> int:
    """Devolve a coleção da categoria — e é essa coleção que o produto passa a
    carregar.

    DECISÃO: trocar a categoria TROCA a coleção junto, inclusive em lote.
    Trocar uma sem a outra estoura a FK composta
    (fk_produtos_categoria_colecao_categorias) com 500; e recusar a troca entre
    coleções tornaria impossível mover uma bolsa do Feminino para o Masculino
    pelo painel, que é correção corriqueira de cadastro errado.
    """
    colecao_id = sessao.scalar(
        select(Categoria.colecao_id).where(Categoria.id == categoria_id)
    )
    if colecao_id is None:
        raise _campo_invalido("categoriaId", "Categoria não encontrada.")
    return colecao_id


def _proxima_ordem_de_destaque(sessao: Session) -> int:
    """`ck_produtos_destaque_ordem` exige ordem quando destaque é verdadeiro.
    Em vez de recusar o salvamento por causa de um campo que a tela nem mostra,
    o produto entra no fim da fila de destaques."""
    return (sessao.scalar(select(func.max(Produto.destaque_ordem))) or 0) + 1


def _ajustar_destaque(sessao: Session, produto: Produto) -> None:
    if produto.destaque and produto.destaque_ordem is None:
        produto.destaque_ordem = _proxima_ordem_de_destaque(sessao)
    if not produto.destaque:
        produto.destaque_ordem = None


def _codigo_ja_existe(sessao: Session, codigo: str, ignorar_id: int | None = None) -> bool:
    consulta = select(Produto.id).where(Produto.codigo == codigo)
    if ignorar_id is not None:
        consulta = consulta.where(Produto.id != ignorar_id)
    return sessao.scalar(consulta) is not None


def criar_produto(sessao: Session, dados: ProdutoCriar) -> ProdutoAdminDetalhe:
    _conferir_marca(sessao, dados.marca_id)
    colecao_id = _colecao_da_categoria(sessao, dados.categoria_id)

    produto = Produto(
        nome=dados.nome.strip(),
        descricao=dados.descricao,
        status=dados.status,
        destaque=dados.destaque,
        destaque_ordem=dados.destaque_ordem,
        marca_id=dados.marca_id,
        categoria_id=dados.categoria_id,
        colecao_id=colecao_id,
    )
    _ajustar_destaque(sessao, produto)

    if dados.codigo:
        produto.codigo = dados.codigo.strip().upper()
        if _codigo_ja_existe(sessao, produto.codigo):
            raise _codigo_em_uso(produto.codigo)
        try:
            sessao.add(produto)
            sessao.commit()
        except IntegrityError as erro:
            sessao.rollback()
            # A conferência acima resolve o caso comum; este `except` é a
            # corrida entre duas pessoas salvando o MESMO código no mesmo
            # instante, que nenhuma conferência prévia pega.
            if _e_colisao_de_codigo(erro):
                raise _codigo_em_uso(produto.codigo) from erro
            raise
    else:
        _gravar_com_codigo_gerado(sessao, produto, _prefixo_da_marca(sessao, dados.marca_id))

    return obter_produto(sessao, produto.id)


def editar_produto(
    sessao: Session, produto_id: int, dados: ProdutoEditar
) -> ProdutoAdminDetalhe:
    produto = _carregar(sessao, produto_id)
    # `model_fields_set` distingue "não mandou o campo" de "mandou null": sem
    # isso, todo PATCH apagaria a descrição de quem não a editou.
    informados = dados.model_fields_set

    if "categorias_ids" in informados:
        if "categoria_id" in informados:
            raise _campo_invalido("categoriasIds", "Envie categoriasIds ou categoriaId, nunca os dois.")
        definir_destinos(sessao, produto, validar_destinos(sessao, dados.categorias_ids))

    if "codigo" in informados and dados.codigo:
        novo = dados.codigo.strip().upper()
        if _codigo_ja_existe(sessao, novo, ignorar_id=produto.id):
            raise _codigo_em_uso(novo)
        produto.codigo = novo

    if "nome" in informados and dados.nome:
        produto.nome = dados.nome.strip()
    if "descricao" in informados:
        produto.descricao = dados.descricao
    if "status" in informados and dados.status:
        produto.status = dados.status
    if "marca_id" in informados and dados.marca_id is not None:
        _conferir_marca(sessao, dados.marca_id)
        produto.marca_id = dados.marca_id
    if "categoria_id" in informados and dados.categoria_id is not None and "categorias_ids" not in informados:
        produto.colecao_id = _colecao_da_categoria(sessao, dados.categoria_id)
        produto.categoria_id = dados.categoria_id
        sessao.execute(delete(ProdutoCategoriaAdicional).where(ProdutoCategoriaAdicional.produto_id == produto.id))

    if "destaque" in informados and dados.destaque is not None:
        produto.destaque = dados.destaque
    if "destaque_ordem" in informados:
        produto.destaque_ordem = dados.destaque_ordem
    _ajustar_destaque(sessao, produto)

    produto.atualizado_em = datetime.now(timezone.utc)
    try:
        sessao.commit()
    except IntegrityError as erro:
        sessao.rollback()
        if _e_colisao_de_codigo(erro):
            raise _codigo_em_uso(produto.codigo) from erro
        raise

    return obter_produto(sessao, produto.id)


def excluir_produto(sessao: Session, produto_id: int) -> None:
    """Imagens, variações, favoritos e itens de carrinho somem junto;
    `selecao_itens` fica, com `produto_id` nulo e o texto congelado intacto,
    porque é o histórico do que o cliente enviou e não pode depender de o
    produto ainda existir.

    AS VARIAÇÕES SAEM PRIMEIRO, por `remover_variacoes` — a mesma porta que a
    substituição do conjunto usa. Apagar o produto apagaria as variações pela
    cascata, e aí o `ON DELETE SET NULL` da FK no carrinho deixaria um item com
    (tamanho, cor) = (nulo, nulo) colidindo com outro item do MESMO produto no
    MESMO carrinho, sob NULLS NOT DISTINCT. `remover_variacoes` funde esses
    itens antes; o DELETE do produto leva embora o que sobrar.

    Por isso também é DELETE do Core e não `sessao.delete(produto)`: o ORM
    apagaria as variações por conta própria, pelo `cascade="all, delete-orphan"`
    do modelo, sem passar por essa resolução.
    """
    produto = _carregar(sessao, produto_id)
    ids_variacoes = list(
        sessao.scalars(
            select(ProdutoVariacao.id).where(ProdutoVariacao.produto_id == produto.id)
        )
    )
    remover_variacoes(sessao, ids_variacoes)
    sessao.execute(delete(Produto).where(Produto.id == produto.id))
    sessao.commit()


def duplicar_produto(sessao: Session, produto_id: int) -> ProdutoAdminDetalhe:
    """Cópia com código novo, imagens e variações.

    A cópia nasce OCULTA e sem destaque: duplicar é o primeiro passo de um
    cadastro que ainda vai ser editado, e uma gêmea publicada na hora aparece
    na vitrine com o nome da original e um "(cópia)" no fim.
    """
    original = _carregar(sessao, produto_id)

    copia = Produto(
        nome=(original.nome + SUFIXO_COPIA)[:180],
        descricao=original.descricao,
        status="oculto",
        destaque=False,
        destaque_ordem=None,
        marca_id=original.marca_id,
        categoria_id=original.categoria_id,
        colecao_id=original.colecao_id,
    )
    _gravar_com_codigo_gerado(sessao, copia, _prefixo_da_marca(sessao, original.marca_id))

    for categoria_id in sessao.scalars(select(ProdutoCategoriaAdicional.categoria_id).where(
        ProdutoCategoriaAdicional.produto_id == original.id
    )).all():
        sessao.add(ProdutoCategoriaAdicional(produto_id=copia.id, categoria_id=categoria_id))

    imagens = sessao.scalars(
        select(ProdutoImagem)
        .where(ProdutoImagem.produto_id == original.id)
        .order_by(ProdutoImagem.ordem.asc(), ProdutoImagem.id.asc())
    ).all()
    for imagem in imagens:
        sessao.add(
            ProdutoImagem(
                produto_id=copia.id,
                url=imagem.url,
                alt=imagem.alt,
                ordem=imagem.ordem,
                capa=imagem.capa,
            )
        )

    variacoes = sessao.scalars(
        select(ProdutoVariacao)
        .where(ProdutoVariacao.produto_id == original.id)
        .order_by(
            ProdutoVariacao.tipo.asc(), ProdutoVariacao.ordem.asc(), ProdutoVariacao.id.asc()
        )
    ).all()
    for variacao in variacoes:
        sessao.add(
            ProdutoVariacao(
                produto_id=copia.id,
                tipo=variacao.tipo,
                valor=variacao.valor,
                # A cópia aponta para a MESMA cor do vocabulário: sem isto a
                # ck_produto_variacoes_cor_id recusaria a variação de cor.
                cor_id=variacao.cor_id,
                disponivel=variacao.disponivel,
                ordem=variacao.ordem,
            )
        )

    sessao.commit()
    return obter_produto(sessao, copia.id)


# ======================================================================
# Alteração em lote
# ======================================================================


def alterar_em_lote(
    sessao: Session,
    ids: list[int],
    status: str | None,
    destaque: bool | None,
    marca_id: int | None,
    categoria_id: int | None,
) -> int:
    """Tudo ou nada. Se um id não existir, NADA muda e a rota devolve a lista
    dos ids problemáticos: alterar 19 de 20 deixaria a tela mostrando um
    resultado que não corresponde ao banco, e ninguém saberia qual linha ficou
    para trás."""
    pedidos = list(dict.fromkeys(ids))
    existentes = set(sessao.scalars(select(Produto.id).where(Produto.id.in_(pedidos))))
    faltando = [identificador for identificador in pedidos if identificador not in existentes]
    if faltando:
        raise AppError(
            codigo=PRODUTO_NAO_ENCONTRADO,
            mensagem="Nenhuma alteração foi feita: há produtos que não existem mais.",
            status_code=404,
            campos={"ids": "Atualize a listagem e tente de novo."},
            detalhes={"naoEncontrados": faltando},
        )

    valores: dict = {}
    if status is not None:
        valores["status"] = status
    if marca_id is not None:
        _conferir_marca(sessao, marca_id)
        valores["marca_id"] = marca_id
    if categoria_id is not None:
        # A coleção vai junto — ver _colecao_da_categoria.
        valores["colecao_id"] = _colecao_da_categoria(sessao, categoria_id)
        valores["categoria_id"] = categoria_id
        sessao.execute(delete(ProdutoCategoriaAdicional).where(ProdutoCategoriaAdicional.produto_id.in_(pedidos)))
    if destaque is not None:
        valores["destaque"] = destaque
        if destaque:
            # ck_produtos_destaque_ordem é conferida LINHA A LINHA, no mesmo
            # UPDATE: ligar o destaque agora e numerar depois derruba a
            # instrução. Por isso a ordem entra junto, como CASE por id, e o
            # coalesce preserva a posição de quem já era destaque.
            proxima = _proxima_ordem_de_destaque(sessao)
            numeracao = {
                identificador: proxima + passo
                for passo, identificador in enumerate(sorted(pedidos))
            }
            valores["destaque_ordem"] = func.coalesce(
                Produto.destaque_ordem, case(numeracao, value=Produto.id)
            )
        else:
            valores["destaque_ordem"] = None

    if not valores:
        raise _campo_invalido("status", "Informe ao menos um campo para alterar.")

    valores["atualizado_em"] = datetime.now(timezone.utc)

    # `update()` do Core é seguro aqui: nenhum dos quatro campos alimenta o
    # listener de `nome_ordenacao`, que só depende do nome.
    resultado = sessao.execute(
        update(Produto).where(Produto.id.in_(pedidos)).values(**valores)
    )

    sessao.commit()
    return resultado.rowcount or 0
