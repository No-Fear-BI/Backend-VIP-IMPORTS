"""CRUD de categorias no painel (tarefa 57).

O slug da categoria é único POR COLEÇÃO, não global: "bolsas" existe em
Feminino e em Masculino, e são categorias diferentes. É o que a restrição
uq_categorias_colecao_slug diz desde a 0001, e é por isso que a URL pública
precisa das duas coisas (`?colecao=feminino&categoria=bolsas`).

TROCAR A COLEÇÃO DE UMA CATEGORIA COM PRODUTOS: recusado com 409.

A FK composta fk_produtos_categoria_colecao_categorias amarra
produtos (categoria_id, colecao_id) a categorias (id, colecao_id). Ela NÃO é
adiável, então não existe ordem de instruções que mova as duas pontas juntas
dentro da mesma transação: mexer na categoria primeiro quebra os produtos que
ainda apontam para a coleção antiga, e mexer nos produtos primeiro os deixa
apontando para um par que ainda não existe. Mover a categoria junto com os
produtos exigiria tornar a FK adiável — mudança de schema para um caso que,
além disso, é decisão de negócio: passar 600 produtos de Feminino para
Masculino não é efeito colateral de corrigir um cadastro.

O caminho que existe para isso é o outro: criar a categoria na coleção certa e
mover os produtos com `PATCH /admin/produtos/lote`, que move a coleção junto —
é o que a mensagem do 409 manda fazer. Categoria SEM produto troca de coleção
normalmente.
"""

from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from vip_api.erros.codigos import (
    CATEGORIA_COM_PRODUTOS,
    CATEGORIA_NAO_ENCONTRADA,
    COLECAO_NAO_ENCONTRADA,
    SLUG_EM_USO,
)
from vip_api.erros.excecoes import AppError
from vip_api.esquemas.admin_catalogo import (
    CategoriaAdmin,
    CategoriaCriar,
    CategoriaEditar,
)
from vip_api.modelos.catalogo import Categoria, Colecao, Produto
from vip_api.texto import gerar_slug

TENTATIVAS_DE_SLUG = 50


def _nao_encontrada() -> AppError:
    return AppError(
        codigo=CATEGORIA_NAO_ENCONTRADA,
        mensagem="Categoria não encontrada.",
        status_code=404,
    )


def _slug_em_uso(slug: str, colecao_slug: str) -> AppError:
    return AppError(
        codigo=SLUG_EM_USO,
        mensagem=f"Já existe uma categoria '{slug}' na coleção {colecao_slug}.",
        status_code=409,
        campos={"slug": "Este slug já existe nesta coleção."},
    )


def _carregar(sessao: Session, categoria_id: int) -> Categoria:
    categoria = sessao.get(Categoria, categoria_id)
    if categoria is None:
        raise _nao_encontrada()
    return categoria


def _colecao(sessao: Session, colecao_id: int) -> Colecao:
    colecao = sessao.get(Colecao, colecao_id)
    if colecao is None:
        raise AppError(
            codigo=COLECAO_NAO_ENCONTRADA,
            mensagem="Coleção não encontrada.",
            status_code=400,
            campos={"colecaoId": "Coleção não encontrada."},
        )
    return colecao


def _slug_livre(
    sessao: Session, colecao_id: int, slug: str, ignorar_id: int | None = None
) -> bool:
    consulta = select(Categoria.id).where(
        Categoria.colecao_id == colecao_id, Categoria.slug == slug
    )
    if ignorar_id is not None:
        consulta = consulta.where(Categoria.id != ignorar_id)
    return sessao.scalar(consulta) is None


def _slug_gerado(sessao: Session, colecao_id: int, nome: str) -> str:
    base = gerar_slug(nome) or "categoria"
    if _slug_livre(sessao, colecao_id, base):
        return base
    for sufixo in range(2, TENTATIVAS_DE_SLUG + 2):
        candidato = f"{base}-{sufixo}"
        if _slug_livre(sessao, colecao_id, candidato):
            return candidato
    raise _slug_em_uso(base, str(colecao_id))


def _total_por_categoria(sessao: Session, ids: list[int]) -> dict[int, int]:
    if not ids:
        return {}
    linhas = sessao.execute(
        select(Produto.categoria_id, func.count())
        .where(Produto.categoria_id.in_(ids))
        .group_by(Produto.categoria_id)
    ).all()
    return {categoria_id: total for categoria_id, total in linhas}


def _montar(categoria: Categoria, colecao_slug: str, total: int) -> CategoriaAdmin:
    return CategoriaAdmin(
        id=categoria.id,
        colecao_id=categoria.colecao_id,
        colecao_slug=colecao_slug,
        nome=categoria.nome,
        slug=categoria.slug,
        imagem_url=categoria.imagem_url,
        destaque=categoria.destaque,
        destaque_ordem=categoria.destaque_ordem,
        ordem=categoria.ordem,
        ativa=categoria.ativa,
        total_produtos=total,
        criado_em=categoria.criado_em,
        atualizado_em=categoria.atualizado_em,
    )


def _um(sessao: Session, categoria: Categoria) -> CategoriaAdmin:
    colecao_slug = sessao.scalar(
        select(Colecao.slug).where(Colecao.id == categoria.colecao_id)
    )
    totais = _total_por_categoria(sessao, [categoria.id])
    return _montar(categoria, colecao_slug, totais.get(categoria.id, 0))


def listar_categorias(
    sessao: Session, colecao_id: int | None = None
) -> list[CategoriaAdmin]:
    consulta = (
        select(Categoria, Colecao.slug.label("colecao_slug"))
        .join(Colecao, Colecao.id == Categoria.colecao_id)
        .order_by(Colecao.ordem.asc(), Categoria.ordem.asc(), Categoria.nome.asc())
    )
    if colecao_id is not None:
        consulta = consulta.where(Categoria.colecao_id == colecao_id)

    linhas = sessao.execute(consulta).all()
    totais = _total_por_categoria(sessao, [linha[0].id for linha in linhas])
    return [
        _montar(linha[0], linha.colecao_slug, totais.get(linha[0].id, 0))
        for linha in linhas
    ]


def criar_categoria(sessao: Session, dados: CategoriaCriar) -> CategoriaAdmin:
    colecao = _colecao(sessao, dados.colecao_id)

    if dados.slug:
        slug = gerar_slug(dados.slug)
        if not _slug_livre(sessao, colecao.id, slug):
            raise _slug_em_uso(slug, colecao.slug)
    else:
        slug = _slug_gerado(sessao, colecao.id, dados.nome)

    categoria = Categoria(
        colecao_id=colecao.id,
        nome=dados.nome.strip(),
        slug=slug,
        imagem_url=dados.imagem_url,
        destaque=dados.destaque,
        destaque_ordem=dados.destaque_ordem,
        ordem=dados.ordem,
        ativa=dados.ativa,
    )
    _ajustar_destaque(sessao, categoria)
    sessao.add(categoria)
    sessao.commit()
    sessao.refresh(categoria)
    return _um(sessao, categoria)


def _ajustar_destaque(sessao: Session, categoria: Categoria) -> None:
    """ck_categorias_destaque_ordem exige ordem quando destaque é verdadeiro —
    mesma regra dos produtos: em vez de recusar o salvamento por um campo que a
    tela nem mostra, a categoria entra no fim da fila."""
    if categoria.destaque and categoria.destaque_ordem is None:
        categoria.destaque_ordem = (
            sessao.scalar(select(func.max(Categoria.destaque_ordem))) or 0
        ) + 1
    if not categoria.destaque:
        categoria.destaque_ordem = None


def editar_categoria(
    sessao: Session, categoria_id: int, dados: CategoriaEditar
) -> CategoriaAdmin:
    categoria = _carregar(sessao, categoria_id)
    informados = dados.model_fields_set
    colecao_id = categoria.colecao_id

    if "colecao_id" in informados and dados.colecao_id is not None:
        colecao_id = _colecao(sessao, dados.colecao_id).id

    if colecao_id != categoria.colecao_id:
        total = sessao.scalar(
            select(func.count())
            .select_from(Produto)
            .where(Produto.categoria_id == categoria.id)
        )
        if total:
            raise AppError(
                codigo=CATEGORIA_COM_PRODUTOS,
                mensagem=(
                    f"Não é possível mudar a coleção: {total} produtos usam esta "
                    "categoria. Crie a categoria na outra coleção e mova os "
                    "produtos por PATCH /admin/produtos/lote."
                ),
                status_code=409,
                campos={"colecaoId": "Mova os produtos antes."},
                detalhes={"totalProdutos": total},
            )

    # Slug: mesma regra da marca — trocar o nome não mexe na URL.
    if "slug" in informados and dados.slug:
        novo = gerar_slug(dados.slug)
        if not _slug_livre(sessao, colecao_id, novo, ignorar_id=categoria.id):
            raise _slug_em_uso(novo, _colecao(sessao, colecao_id).slug)
        categoria.slug = novo
    elif colecao_id != categoria.colecao_id:
        # Mudou de coleção com o mesmo slug: o par (coleção, slug) pode já
        # existir do outro lado.
        if not _slug_livre(sessao, colecao_id, categoria.slug, ignorar_id=categoria.id):
            raise _slug_em_uso(categoria.slug, _colecao(sessao, colecao_id).slug)

    categoria.colecao_id = colecao_id

    if "nome" in informados and dados.nome:
        categoria.nome = dados.nome.strip()
    if "imagem_url" in informados:
        categoria.imagem_url = dados.imagem_url
    if "ordem" in informados and dados.ordem is not None:
        categoria.ordem = dados.ordem
    if "ativa" in informados and dados.ativa is not None:
        categoria.ativa = dados.ativa
    if "destaque" in informados and dados.destaque is not None:
        categoria.destaque = dados.destaque
    if "destaque_ordem" in informados:
        categoria.destaque_ordem = dados.destaque_ordem
    _ajustar_destaque(sessao, categoria)

    categoria.atualizado_em = datetime.now(timezone.utc)
    sessao.commit()
    sessao.refresh(categoria)
    return _um(sessao, categoria)


def excluir_categoria(sessao: Session, categoria_id: int) -> None:
    categoria = _carregar(sessao, categoria_id)
    total = sessao.scalar(
        select(func.count())
        .select_from(Produto)
        .where(Produto.categoria_id == categoria.id)
    )
    if total:
        raise AppError(
            codigo=CATEGORIA_COM_PRODUTOS,
            mensagem=f"Não é possível excluir: {total} produtos usam esta categoria.",
            status_code=409,
            campos={"categoriaId": "Mova ou exclua os produtos antes."},
            detalhes={"totalProdutos": total},
        )

    sessao.execute(delete(Categoria).where(Categoria.id == categoria.id))
    sessao.commit()
