"""CRUD de categorias no painel (tarefa 57; revisto na migração 0015).

Desde a 0015 a categoria NÃO pertence a coleção: o slug é único na tabela toda, e Feminino e
Masculino são o público do produto (`produtos.feminino`/`masculino`), não categoria. "Bolsas"
existe uma vez só; o mesmo vale para um tema como "Coleção de verão".

Excluir categoria com produto continua sendo 409: o caminho é mover os produtos
(`PATCH /admin/produtos/lote` com `categoriaId`) ou esconder a categoria (`ativa: false`), que
a tira da vitrine sem apagar nada.
"""

from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from vip_api.erros.codigos import (
    CATEGORIA_COM_PRODUTOS,
    CATEGORIA_NAO_ENCONTRADA,
    SLUG_EM_USO,
)
from vip_api.erros.excecoes import AppError
from vip_api.esquemas.admin_catalogo import (
    CategoriaAdmin,
    CategoriaCriar,
    CategoriaEditar,
)
from vip_api.modelos.catalogo import Categoria, Produto
from vip_api.servicos.produto_destinos import pertence_categoria
from vip_api.texto import gerar_slug

TENTATIVAS_DE_SLUG = 50


def _nao_encontrada() -> AppError:
    return AppError(
        codigo=CATEGORIA_NAO_ENCONTRADA,
        mensagem="Categoria não encontrada.",
        status_code=404,
    )


def _slug_em_uso(slug: str) -> AppError:
    return AppError(
        codigo=SLUG_EM_USO,
        mensagem=f"Já existe uma categoria '{slug}'.",
        status_code=409,
        campos={"slug": "Este slug já existe."},
    )


def _carregar(sessao: Session, categoria_id: int) -> Categoria:
    categoria = sessao.get(Categoria, categoria_id)
    if categoria is None:
        raise _nao_encontrada()
    return categoria


def _slug_livre(sessao: Session, slug: str, ignorar_id: int | None = None) -> bool:
    consulta = select(Categoria.id).where(Categoria.slug == slug)
    if ignorar_id is not None:
        consulta = consulta.where(Categoria.id != ignorar_id)
    return sessao.scalar(consulta) is None


def _slug_gerado(sessao: Session, nome: str) -> str:
    base = gerar_slug(nome) or "categoria"
    if _slug_livre(sessao, base):
        return base
    for sufixo in range(2, TENTATIVAS_DE_SLUG + 2):
        candidato = f"{base}-{sufixo}"
        if _slug_livre(sessao, candidato):
            return candidato
    raise _slug_em_uso(base)


def _total_por_categoria(sessao: Session, ids: list[int]) -> dict[int, int]:
    if not ids:
        return {}
    linhas = sessao.execute(
        select(Categoria.id, func.count(Produto.id))
        .join(Produto, pertence_categoria(Categoria.id))
        .where(Categoria.id.in_(ids))
        .group_by(Categoria.id)
    ).all()
    return {categoria_id: total for categoria_id, total in linhas}


def _montar(categoria: Categoria, total: int) -> CategoriaAdmin:
    return CategoriaAdmin(
        id=categoria.id,
        nome=categoria.nome,
        slug=categoria.slug,
        imagem_url=categoria.imagem_url,
        destaque=categoria.destaque,
        destaque_ordem=categoria.destaque_ordem,
        ordem=categoria.ordem,
        ativa=categoria.ativa,
        card_home=categoria.card_home,
        card_home_imagem_url=categoria.card_home_imagem_url,
        total_produtos=total,
        criado_em=categoria.criado_em,
        atualizado_em=categoria.atualizado_em,
    )


def _um(sessao: Session, categoria: Categoria) -> CategoriaAdmin:
    totais = _total_por_categoria(sessao, [categoria.id])
    return _montar(categoria, totais.get(categoria.id, 0))


def listar_categorias(sessao: Session) -> list[CategoriaAdmin]:
    categorias = sessao.scalars(
        select(Categoria).order_by(Categoria.ordem.asc(), Categoria.nome.asc())
    ).all()
    totais = _total_por_categoria(sessao, [c.id for c in categorias])
    return [_montar(c, totais.get(c.id, 0)) for c in categorias]


def _liberar_card(sessao: Session, lado: str, ignorar_id: int | None = None) -> None:
    """Cada card da home tem UMA categoria: quem já o ocupava sai dele (e perde a imagem do card).
    O flush vem antes de quem entra gravar, por causa do índice único parcial."""
    consulta = select(Categoria).where(Categoria.card_home == lado)
    if ignorar_id is not None:
        consulta = consulta.where(Categoria.id != ignorar_id)
    for anterior in sessao.scalars(consulta):
        anterior.card_home = None
        anterior.card_home_imagem_url = None
    sessao.flush()


def criar_categoria(sessao: Session, dados: CategoriaCriar) -> CategoriaAdmin:
    if dados.slug:
        slug = gerar_slug(dados.slug)
        if not _slug_livre(sessao, slug):
            raise _slug_em_uso(slug)
    else:
        slug = _slug_gerado(sessao, dados.nome)

    categoria = Categoria(
        nome=dados.nome.strip(),
        slug=slug,
        imagem_url=dados.imagem_url,
        destaque=dados.destaque,
        destaque_ordem=dados.destaque_ordem,
        ordem=dados.ordem,
        ativa=dados.ativa,
    )
    if dados.card_home:
        _liberar_card(sessao, dados.card_home)
        categoria.card_home = dados.card_home
        categoria.card_home_imagem_url = dados.card_home_imagem_url
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

    # Slug: mesma regra da marca — trocar o nome não mexe na URL.
    if "slug" in informados and dados.slug:
        novo = gerar_slug(dados.slug)
        if not _slug_livre(sessao, novo, ignorar_id=categoria.id):
            raise _slug_em_uso(novo)
        categoria.slug = novo

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

    if "card_home" in informados:
        if dados.card_home:
            _liberar_card(sessao, dados.card_home, ignorar_id=categoria.id)
            categoria.card_home = dados.card_home
        else:
            categoria.card_home = None
            categoria.card_home_imagem_url = None
    if "card_home_imagem_url" in informados and (categoria.card_home or "card_home" not in informados):
        categoria.card_home_imagem_url = dados.card_home_imagem_url if categoria.card_home else None

    categoria.atualizado_em = datetime.now(timezone.utc)
    sessao.commit()
    sessao.refresh(categoria)
    return _um(sessao, categoria)


def excluir_categoria(sessao: Session, categoria_id: int) -> None:
    categoria = _carregar(sessao, categoria_id)
    total = sessao.scalar(
        select(func.count())
        .select_from(Produto)
        .where(pertence_categoria(categoria.id))
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
