"""CRUD de marcas no painel (tarefa 57).

DUAS REGRAS QUE VALEM MAIS QUE O RESTO DO ARQUIVO:

1. O slug é a URL pública da marca (`/marcas/chanel`) e tem milhares de
   produtos pendurados nela. Ele nasce do nome na CRIAÇÃO e não muda mais
   sozinho: editar o nome de "chanel" para "Chanel" não pode derrubar o link
   que o cliente mandou no WhatsApp nem o que o buscador já indexou (tarefa
   81). Para trocar o slug, o corpo precisa mandar `slug` explicitamente — aí
   é decisão consciente de quem está editando.
2. Marca com produto NÃO é excluída. 409 com a contagem, para a tela dizer
   "643 produtos usam esta marca" em vez de um "não deu" sem explicação.
   Produto órfão não existe neste banco: a FK é RESTRICT.
"""

from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from vip_api.erros.codigos import (
    MARCA_COM_PRODUTOS,
    MARCA_NAO_ENCONTRADA,
    SLUG_EM_USO,
)
from vip_api.erros.excecoes import AppError
from vip_api.esquemas.admin_catalogo import MarcaAdmin, MarcaCriar, MarcaEditar
from vip_api.modelos.catalogo import Marca, Produto
from vip_api.texto import gerar_slug

TENTATIVAS_DE_SLUG = 50


def _nao_encontrada() -> AppError:
    return AppError(
        codigo=MARCA_NAO_ENCONTRADA, mensagem="Marca não encontrada.", status_code=404
    )


def _slug_em_uso(slug: str) -> AppError:
    return AppError(
        codigo=SLUG_EM_USO,
        mensagem=f"O slug '{slug}' já está em uso por outra marca.",
        status_code=409,
        campos={"slug": "Este slug já está em uso."},
    )


def _carregar(sessao: Session, marca_id: int) -> Marca:
    marca = sessao.get(Marca, marca_id)
    if marca is None:
        raise _nao_encontrada()
    return marca


def _slug_livre(sessao: Session, slug: str, ignorar_id: int | None = None) -> bool:
    consulta = select(Marca.id).where(Marca.slug == slug)
    if ignorar_id is not None:
        consulta = consulta.where(Marca.id != ignorar_id)
    return sessao.scalar(consulta) is None


def _slug_gerado(sessao: Session, nome: str) -> str:
    """Slug a partir do nome, com sufixo numérico se já existir.

    Só vale para o slug GERADO: quando quem edita manda o slug na mão, colisão
    vira 409 — inventar "chanel-2" para quem digitou "chanel" seria criar uma
    URL que ninguém pediu.
    """
    base = gerar_slug(nome) or "marca"
    if _slug_livre(sessao, base):
        return base
    for sufixo in range(2, TENTATIVAS_DE_SLUG + 2):
        candidato = f"{base}-{sufixo}"
        if _slug_livre(sessao, candidato):
            return candidato
    raise _slug_em_uso(base)


def _total_por_marca(sessao: Session, marca_ids: list[int]) -> dict[int, int]:
    """Contagem numa consulta só, para a listagem não virar um COUNT por
    marca dentro do laço."""
    if not marca_ids:
        return {}
    linhas = sessao.execute(
        select(Produto.marca_id, func.count())
        .where(Produto.marca_id.in_(marca_ids))
        .group_by(Produto.marca_id)
    ).all()
    return {marca_id: total for marca_id, total in linhas}


def _montar(marca: Marca, total: int) -> MarcaAdmin:
    return MarcaAdmin(
        id=marca.id,
        nome=marca.nome,
        slug=marca.slug,
        logo_url=marca.logo_url,
        ordem=marca.ordem,
        ativa=marca.ativa,
        total_produtos=total,
        criado_em=marca.criado_em,
        atualizado_em=marca.atualizado_em,
    )


def listar_marcas(sessao: Session) -> list[MarcaAdmin]:
    """Todas, inclusive as inativas e as sem produto — são 18 linhas, não
    precisa de paginação. A contagem inclui produto oculto: é o painel."""
    marcas = list(
        sessao.scalars(select(Marca).order_by(Marca.ordem.asc(), Marca.nome.asc()))
    )
    totais = _total_por_marca(sessao, [m.id for m in marcas])
    return [_montar(marca, totais.get(marca.id, 0)) for marca in marcas]


def criar_marca(sessao: Session, dados: MarcaCriar) -> MarcaAdmin:
    if dados.slug:
        slug = gerar_slug(dados.slug)
        if not _slug_livre(sessao, slug):
            raise _slug_em_uso(slug)
    else:
        slug = _slug_gerado(sessao, dados.nome)

    # Objeto ORM, não INSERT do Core: `nome_busca` é preenchida por listener do
    # modelo, e sem ela a marca não aparece na busca do site.
    marca = Marca(
        nome=dados.nome.strip(),
        slug=slug,
        logo_url=dados.logo_url,
        ordem=dados.ordem,
        ativa=dados.ativa,
    )
    sessao.add(marca)
    sessao.commit()
    sessao.refresh(marca)
    return _montar(marca, 0)


def editar_marca(sessao: Session, marca_id: int, dados: MarcaEditar) -> MarcaAdmin:
    marca = _carregar(sessao, marca_id)
    informados = dados.model_fields_set

    # O slug NÃO é recalculado a partir do nome. Só muda se veio no corpo.
    if "slug" in informados and dados.slug:
        novo = gerar_slug(dados.slug)
        if not _slug_livre(sessao, novo, ignorar_id=marca.id):
            raise _slug_em_uso(novo)
        marca.slug = novo

    if "nome" in informados and dados.nome:
        marca.nome = dados.nome.strip()
    if "logo_url" in informados:
        marca.logo_url = dados.logo_url
    if "ordem" in informados and dados.ordem is not None:
        marca.ordem = dados.ordem
    if "ativa" in informados and dados.ativa is not None:
        marca.ativa = dados.ativa

    marca.atualizado_em = datetime.now(timezone.utc)
    sessao.commit()
    sessao.refresh(marca)
    return _montar(marca, _total_por_marca(sessao, [marca.id]).get(marca.id, 0))


def excluir_marca(sessao: Session, marca_id: int) -> None:
    marca = _carregar(sessao, marca_id)
    total = sessao.scalar(
        select(func.count()).select_from(Produto).where(Produto.marca_id == marca.id)
    )
    if total:
        raise AppError(
            codigo=MARCA_COM_PRODUTOS,
            mensagem=f"Não é possível excluir: {total} produtos usam esta marca.",
            status_code=409,
            campos={"marcaId": "Mova ou exclua os produtos antes."},
            detalhes={"totalProdutos": total},
        )

    sessao.execute(delete(Marca).where(Marca.id == marca.id))
    sessao.commit()
