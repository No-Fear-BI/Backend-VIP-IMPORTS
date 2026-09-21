"""CRUD do vocabulário de cores no painel (revisão 0007).

Espelha admin_marcas.py, com uma diferença que vale o arquivo inteiro:

**Renomear uma cor reescreve o texto exibido nas variações que apontam para
ela.** Marca não tem esse problema (o produto guarda `marca_id`, e o nome sai
do JOIN), mas `produto_variacoes.valor` é texto copiado — é ele que a vitrine
mostra e o WhatsApp recebe. Se o dono corrige "preto" para "Preto" e as
variações ficassem como estavam, a paleta do painel diria uma coisa e a peça
diria outra até alguém reabrir a grade de cada produto.

Reescrever esbarra na UNIQUE `(produto_id, tipo, valor)`: um produto que já
tenha "Preto" e "preto" como variações separadas (dado anterior à 0007, que
não normalizou grafia de propósito) não aceita as duas viraram o mesmo texto.
Isso é 409 COR_EM_CONFLITO com o código do produto, e não uma exclusão
silenciosa — a variação que sumiria pode ser a que está no carrinho de alguém.
"""

from datetime import datetime, timezone

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from vip_api.erros.codigos import (
    COR_EM_CONFLITO,
    COR_EM_USO,
    COR_NAO_ENCONTRADA,
    SLUG_EM_USO,
)
from vip_api.erros.excecoes import AppError
from vip_api.esquemas.admin_catalogo import CorAdmin, CorCriar, CorEditar
from vip_api.modelos.catalogo import Cor, Produto, ProdutoVariacao
from vip_api.texto import gerar_slug

TENTATIVAS_DE_SLUG = 50


def _nao_encontrada() -> AppError:
    return AppError(codigo=COR_NAO_ENCONTRADA, mensagem="Cor não encontrada.", status_code=404)


def _slug_em_uso(slug: str) -> AppError:
    return AppError(
        codigo=SLUG_EM_USO,
        mensagem=f"O slug '{slug}' já está em uso por outra cor.",
        status_code=409,
        campos={"slug": "Este slug já está em uso."},
    )


def _carregar(sessao: Session, cor_id: int) -> Cor:
    cor = sessao.get(Cor, cor_id)
    if cor is None:
        raise _nao_encontrada()
    return cor


def _slug_livre(sessao: Session, slug: str, ignorar_id: int | None = None) -> bool:
    consulta = select(Cor.id).where(Cor.slug == slug)
    if ignorar_id is not None:
        consulta = consulta.where(Cor.id != ignorar_id)
    return sessao.scalar(consulta) is None


def _slug_gerado(sessao: Session, nome: str) -> str:
    """Slug a partir do nome, com sufixo numérico se já existir. Slug mandado
    na mão que colide vira 409 — ver admin_marcas._slug_gerado."""
    base = gerar_slug(nome) or "cor"
    if _slug_livre(sessao, base):
        return base
    for sufixo in range(2, TENTATIVAS_DE_SLUG + 2):
        candidato = f"{base}-{sufixo}"
        if _slug_livre(sessao, candidato):
            return candidato
    raise _slug_em_uso(base)


def _total_por_cor(sessao: Session, cor_ids: list[int]) -> dict[int, int]:
    """PRODUTOS distintos por cor, numa consulta só.

    `count(DISTINCT produto_id)` e não `count(*)`: um produto com "Preto" em
    duas variações (grafias diferentes, dado pré-0007) contaria duas vezes, e a
    tela prometeria mais produtos do que existem.
    """
    if not cor_ids:
        return {}
    linhas = sessao.execute(
        select(ProdutoVariacao.cor_id, func.count(func.distinct(ProdutoVariacao.produto_id)))
        .where(ProdutoVariacao.cor_id.in_(cor_ids))
        .group_by(ProdutoVariacao.cor_id)
    ).all()
    return {cor_id: total for cor_id, total in linhas}


def _montar(cor: Cor, total: int) -> CorAdmin:
    return CorAdmin(
        id=cor.id,
        nome=cor.nome,
        slug=cor.slug,
        ordem=cor.ordem,
        ativa=cor.ativa,
        total_produtos=total,
        criado_em=cor.criado_em,
        atualizado_em=cor.atualizado_em,
    )


def listar_cores(sessao: Session) -> list[CorAdmin]:
    """Todas, inclusive as inativas e as sem produto — a paleta de uma loja é
    dezenas de linhas, não precisa de paginação."""
    cores = list(sessao.scalars(select(Cor).order_by(Cor.ordem.asc(), Cor.nome.asc())))
    totais = _total_por_cor(sessao, [c.id for c in cores])
    return [_montar(cor, totais.get(cor.id, 0)) for cor in cores]


def criar_cor(sessao: Session, dados: CorCriar) -> CorAdmin:
    if dados.slug:
        slug = gerar_slug(dados.slug)
        if not _slug_livre(sessao, slug):
            raise _slug_em_uso(slug)
    else:
        slug = _slug_gerado(sessao, dados.nome)

    cor = Cor(nome=dados.nome.strip(), slug=slug, ordem=dados.ordem, ativa=dados.ativa)
    sessao.add(cor)
    sessao.commit()
    sessao.refresh(cor)
    return _montar(cor, 0)


def _produto_em_conflito(sessao: Session, cor: Cor, nome_novo: str) -> str | None:
    """O código do primeiro produto que já tem uma variação de cor com o nome
    novo vindo de OUTRA cor. É esse produto que a UNIQUE recusaria."""
    outra = (
        select(ProdutoVariacao.produto_id)
        .where(
            ProdutoVariacao.tipo == "cor",
            ProdutoVariacao.valor == nome_novo,
            ProdutoVariacao.cor_id != cor.id,
        )
        .subquery()
    )
    return sessao.scalar(
        select(Produto.codigo)
        .join(ProdutoVariacao, ProdutoVariacao.produto_id == Produto.id)
        .where(ProdutoVariacao.cor_id == cor.id, Produto.id.in_(select(outra.c.produto_id)))
        .limit(1)
    )


def _renomear_variacoes(sessao: Session, cor: Cor, nome_novo: str) -> None:
    codigo = _produto_em_conflito(sessao, cor, nome_novo)
    if codigo is not None:
        raise AppError(
            codigo=COR_EM_CONFLITO,
            mensagem=(
                f"O produto {codigo} já tem uma variação de cor chamada '{nome_novo}'. "
                "Ajuste a grade desse produto antes de renomear."
            ),
            status_code=409,
            campos={"nome": "Já existe esta cor em um produto que usa a cor atual."},
            detalhes={"codigoProduto": codigo},
        )
    try:
        sessao.execute(
            update(ProdutoVariacao)
            .where(ProdutoVariacao.cor_id == cor.id)
            .values(valor=nome_novo, atualizado_em=datetime.now(timezone.utc))
        )
        sessao.flush()
    except IntegrityError as exc:
        # Rede de segurança: a checagem acima roda fora de lock, e duas
        # renomeações simultâneas podem passar por ela. Melhor 409 do que 500.
        sessao.rollback()
        raise AppError(
            codigo=COR_EM_CONFLITO,
            mensagem=f"Já existe uma variação de cor chamada '{nome_novo}' em um produto.",
            status_code=409,
            campos={"nome": "Já existe esta cor em um produto que usa a cor atual."},
        ) from exc


def editar_cor(sessao: Session, cor_id: int, dados: CorEditar) -> CorAdmin:
    cor = _carregar(sessao, cor_id)
    informados = dados.model_fields_set

    # O slug NÃO é recalculado a partir do nome: é a URL do filtro que o
    # cliente pode ter compartilhado. Só muda se veio no corpo.
    if "slug" in informados and dados.slug:
        novo = gerar_slug(dados.slug)
        if not _slug_livre(sessao, novo, ignorar_id=cor.id):
            raise _slug_em_uso(novo)
        cor.slug = novo

    if "nome" in informados and dados.nome:
        nome_novo = dados.nome.strip()
        if nome_novo != cor.nome:
            _renomear_variacoes(sessao, cor, nome_novo)
            cor.nome = nome_novo
    if "ordem" in informados and dados.ordem is not None:
        cor.ordem = dados.ordem
    if "ativa" in informados and dados.ativa is not None:
        cor.ativa = dados.ativa

    cor.atualizado_em = datetime.now(timezone.utc)
    sessao.commit()
    sessao.refresh(cor)
    return _montar(cor, _total_por_cor(sessao, [cor.id]).get(cor.id, 0))


def excluir_cor(sessao: Session, cor_id: int) -> None:
    """Cor em uso NÃO é excluída: 409 com a contagem.

    A FK é RESTRICT, então o banco recusaria de qualquer jeito — mas como 500.
    Contar antes é o que transforma isso em "12 produtos usam esta cor" na tela.
    """
    cor = _carregar(sessao, cor_id)
    total = _total_por_cor(sessao, [cor.id]).get(cor.id, 0)
    if total:
        raise AppError(
            codigo=COR_EM_USO,
            mensagem=f"Não é possível excluir: {total} produtos usam esta cor.",
            status_code=409,
            campos={"corId": "Tire a cor desses produtos antes."},
            detalhes={"totalProdutos": total},
        )

    sessao.execute(delete(Cor).where(Cor.id == cor.id))
    sessao.commit()
