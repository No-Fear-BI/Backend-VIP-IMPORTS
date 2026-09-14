"""CRUD de banners no painel (tarefa 57).

TETO DE QUATRO ATIVOS. A proposta comercial (item 2.1) contratou "banner
principal em carrossel com até 4 imagens administráveis". O teto vale para os
ATIVOS: banner inativo é rascunho, não ocupa espaço no carrossel e pode
existir aos montes. A quinta ativação devolve 400 explicando qual é o limite —
recusar sem dizer o número faria o cliente tentar de novo.

A ordem segue a regra das imagens do produto: 1..N contígua depois de
inserir, reordenar e remover. `GET /home` mostra os ativos nessa ordem.
"""

from datetime import datetime, timezone

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from vip_api.erros.codigos import DADOS_INVALIDOS, PRODUTO_NAO_ENCONTRADO
from vip_api.erros.excecoes import AppError
from vip_api.esquemas.admin_catalogo import (
    LIMITE_BANNERS_ATIVOS,
    BannerAdmin,
    BannerCriar,
    BannerEditar,
)
from vip_api.modelos.catalogo import Banner


def _nao_encontrado() -> AppError:
    return AppError(
        # Não existe BANNER_NAO_ENCONTRADO na lista de códigos do contrato, e
        # criar um só para o painel não ajudaria a tela: a mensagem já diz.
        codigo=PRODUTO_NAO_ENCONTRADO,
        mensagem="Banner não encontrado.",
        status_code=404,
    )


def _carregar(sessao: Session, banner_id: int) -> Banner:
    banner = sessao.get(Banner, banner_id)
    if banner is None:
        raise _nao_encontrado()
    return banner


def _todos(sessao: Session) -> list[Banner]:
    return list(
        sessao.scalars(select(Banner).order_by(Banner.ordem.asc(), Banner.id.asc()))
    )


def _contar_ativos(sessao: Session, ignorar_id: int | None = None) -> int:
    consulta = select(func.count()).select_from(Banner).where(Banner.ativo.is_(True))
    if ignorar_id is not None:
        consulta = consulta.where(Banner.id != ignorar_id)
    return sessao.scalar(consulta) or 0


def _conferir_teto(sessao: Session, ignorar_id: int | None = None) -> None:
    if _contar_ativos(sessao, ignorar_id) >= LIMITE_BANNERS_ATIVOS:
        raise AppError(
            codigo=DADOS_INVALIDOS,
            mensagem=(
                f"O carrossel da home aceita {LIMITE_BANNERS_ATIVOS} banners ativos. "
                "Desative um antes de ativar este."
            ),
            status_code=400,
            campos={"ativo": f"Já há {LIMITE_BANNERS_ATIVOS} banners ativos."},
        )


def _renumerar(sessao: Session, ids_na_ordem: list[int]) -> None:
    for posicao, banner_id in enumerate(ids_na_ordem, start=1):
        sessao.execute(update(Banner).where(Banner.id == banner_id).values(ordem=posicao))


def _montar(banner: Banner) -> BannerAdmin:
    return BannerAdmin(
        id=banner.id,
        titulo=banner.titulo,
        subtitulo=banner.subtitulo,
        imagem_url=banner.imagem_url,
        imagem_url_mobile=banner.imagem_url_mobile,
        alt=banner.alt,
        link_url=banner.link_url,
        ordem=banner.ordem,
        ativo=banner.ativo,
        criado_em=banner.criado_em,
        atualizado_em=banner.atualizado_em,
    )


def listar_banners(sessao: Session) -> list[BannerAdmin]:
    """Ativos e inativos, na ordem do carrossel — o painel precisa ver os
    rascunhos."""
    return [_montar(banner) for banner in _todos(sessao)]


def criar_banner(sessao: Session, dados: BannerCriar) -> BannerAdmin:
    if dados.ativo:
        _conferir_teto(sessao)

    banner = Banner(
        imagem_url=dados.imagem_url,
        imagem_url_mobile=dados.imagem_url_mobile,
        titulo=dados.titulo,
        subtitulo=dados.subtitulo,
        alt=dados.alt,
        link_url=dados.link_url,
        ativo=dados.ativo,
        ordem=len(_todos(sessao)) + 1,
    )
    sessao.add(banner)
    sessao.commit()
    sessao.refresh(banner)
    return _montar(banner)


def editar_banner(sessao: Session, banner_id: int, dados: BannerEditar) -> BannerAdmin:
    banner = _carregar(sessao, banner_id)
    informados = dados.model_fields_set

    if "ativo" in informados and dados.ativo is not None:
        # Só confere quando está LIGANDO: desativar nunca esbarra no teto, e
        # reenviar `ativo: true` num banner que já está ativo também não.
        if dados.ativo and not banner.ativo:
            _conferir_teto(sessao, ignorar_id=banner.id)
        banner.ativo = dados.ativo

    if "imagem_url" in informados and dados.imagem_url:
        banner.imagem_url = dados.imagem_url
    if "imagem_url_mobile" in informados:
        banner.imagem_url_mobile = dados.imagem_url_mobile
    if "titulo" in informados:
        banner.titulo = dados.titulo
    if "subtitulo" in informados:
        banner.subtitulo = dados.subtitulo
    if "alt" in informados:
        banner.alt = dados.alt
    if "link_url" in informados:
        banner.link_url = dados.link_url

    banner.atualizado_em = datetime.now(timezone.utc)
    sessao.commit()
    sessao.refresh(banner)
    return _montar(banner)


def reordenar_banners(sessao: Session, ids_na_ordem: list[int]) -> list[BannerAdmin]:
    """Exige a lista COMPLETA, como as imagens do produto: lista parcial
    reordenaria metade e deixaria a outra metade com a numeração antiga."""
    atuais = {banner.id for banner in _todos(sessao)}
    pedidos = list(dict.fromkeys(ids_na_ordem))

    if len(pedidos) != len(ids_na_ordem) or set(pedidos) != atuais:
        faltando = sorted(atuais - set(pedidos))
        sobrando = sorted(set(pedidos) - atuais)
        raise AppError(
            codigo=DADOS_INVALIDOS,
            mensagem="Há campos inválidos no envio.",
            status_code=400,
            campos={
                "ids": (
                    "A lista precisa trazer todos os banners, e só eles. "
                    f"Faltando: {faltando or '—'}. Inexistentes: {sobrando or '—'}."
                )
            },
        )

    _renumerar(sessao, pedidos)
    sessao.commit()
    return listar_banners(sessao)


def excluir_banner(sessao: Session, banner_id: int) -> list[BannerAdmin]:
    banner = _carregar(sessao, banner_id)
    sessao.execute(delete(Banner).where(Banner.id == banner.id))
    sessao.flush()

    _renumerar(sessao, [b.id for b in _todos(sessao)])
    sessao.commit()
    return listar_banners(sessao)
