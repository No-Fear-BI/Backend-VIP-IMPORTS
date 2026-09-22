"""Rotas de marca, categoria e banner do painel (tarefa 57).

Três roteadores num arquivo só: são CRUDs pequenos e do mesmo domínio. Nenhum
tem proteção própria — todos entram no roteador protegido de admin_painel.py e
herdam o `Depends(exigir_admin)` do grupo.

NÃO existe CRUD de coleções, e não é esquecimento: são duas, fixas, vindas da
migração 0002, e o contrato não tem rota para elas.
"""

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from vip_api.banco import obter_sessao
from vip_api.esquemas.admin_catalogo import (
    BannerAdmin,
    BannerCriar,
    BannerEditar,
    CategoriaAdmin,
    CategoriaCriar,
    CategoriaEditar,
    CorAdmin,
    CorCriar,
    CorEditar,
    MarcaAdmin,
    MarcaCriar,
    MarcaEditar,
    OrdemBanners,
)
from vip_api.servicos.admin_banners import (
    criar_banner,
    editar_banner,
    excluir_banner,
    listar_banners,
    reordenar_banners,
)
from vip_api.servicos.admin_categorias import (
    criar_categoria,
    editar_categoria,
    excluir_categoria,
    listar_categorias,
)
from vip_api.servicos.admin_cores import (
    criar_cor,
    editar_cor,
    excluir_cor,
    listar_cores,
)
from vip_api.servicos.admin_marcas import (
    criar_marca,
    editar_marca,
    excluir_marca,
    listar_marcas,
)

roteador_marcas = APIRouter(prefix="/marcas", tags=["admin"])
roteador_cores = APIRouter(prefix="/cores", tags=["admin"])
roteador_categorias = APIRouter(prefix="/categorias", tags=["admin"])
roteador_banners = APIRouter(prefix="/banners", tags=["admin"])


# ======================================================================
# Marcas
# ======================================================================


@roteador_marcas.get("", response_model=list[MarcaAdmin])
def marcas_listar(sessao: Session = Depends(obter_sessao)) -> list[MarcaAdmin]:
    return listar_marcas(sessao)


@roteador_marcas.post("", response_model=MarcaAdmin, status_code=201)
def marcas_criar(corpo: MarcaCriar, sessao: Session = Depends(obter_sessao)) -> MarcaAdmin:
    return criar_marca(sessao, corpo)


@roteador_marcas.patch("/{marcaId}", response_model=MarcaAdmin)
def marcas_editar(
    corpo: MarcaEditar,
    marca_id: int = Path(alias="marcaId"),
    sessao: Session = Depends(obter_sessao),
) -> MarcaAdmin:
    """Trocar o nome NÃO troca o slug — só mandar `slug` no corpo troca."""
    return editar_marca(sessao, marca_id, corpo)


@roteador_marcas.delete("/{marcaId}")
def marcas_excluir(
    marca_id: int = Path(alias="marcaId"), sessao: Session = Depends(obter_sessao)
) -> dict[str, bool]:
    excluir_marca(sessao, marca_id)
    return {"ok": True}


# ======================================================================
# Cores
# ======================================================================


@roteador_cores.get("", response_model=list[CorAdmin])
def cores_listar(sessao: Session = Depends(obter_sessao)) -> list[CorAdmin]:
    return listar_cores(sessao)


@roteador_cores.post("", response_model=CorAdmin, status_code=201)
def cores_criar(corpo: CorCriar, sessao: Session = Depends(obter_sessao)) -> CorAdmin:
    return criar_cor(sessao, corpo)


@roteador_cores.patch("/{corId}", response_model=CorAdmin)
def cores_editar(
    corpo: CorEditar,
    cor_id: int = Path(alias="corId"),
    sessao: Session = Depends(obter_sessao),
) -> CorAdmin:
    """Trocar o nome reescreve o texto das variações que usam a cor; trocar o
    slug só acontece se `slug` vier no corpo."""
    return editar_cor(sessao, cor_id, corpo)


@roteador_cores.delete("/{corId}")
def cores_excluir(
    cor_id: int = Path(alias="corId"), sessao: Session = Depends(obter_sessao)
) -> dict[str, bool]:
    excluir_cor(sessao, cor_id)
    return {"ok": True}


# ======================================================================
# Categorias
# ======================================================================


@roteador_categorias.get("", response_model=list[CategoriaAdmin])
def categorias_listar(
    colecao_id: int | None = Query(None, alias="colecaoId"),
    sessao: Session = Depends(obter_sessao),
) -> list[CategoriaAdmin]:
    return listar_categorias(sessao, colecao_id)


@roteador_categorias.post("", response_model=CategoriaAdmin, status_code=201)
def categorias_criar(
    corpo: CategoriaCriar, sessao: Session = Depends(obter_sessao)
) -> CategoriaAdmin:
    return criar_categoria(sessao, corpo)


@roteador_categorias.patch("/{categoriaId}", response_model=CategoriaAdmin)
def categorias_editar(
    corpo: CategoriaEditar,
    categoria_id: int = Path(alias="categoriaId"),
    sessao: Session = Depends(obter_sessao),
) -> CategoriaAdmin:
    return editar_categoria(sessao, categoria_id, corpo)


@roteador_categorias.delete("/{categoriaId}")
def categorias_excluir(
    categoria_id: int = Path(alias="categoriaId"),
    sessao: Session = Depends(obter_sessao),
) -> dict[str, bool]:
    excluir_categoria(sessao, categoria_id)
    return {"ok": True}


# ======================================================================
# Banners
# ======================================================================


@roteador_banners.get("", response_model=list[BannerAdmin])
def banners_listar(sessao: Session = Depends(obter_sessao)) -> list[BannerAdmin]:
    return listar_banners(sessao)


@roteador_banners.post("", response_model=BannerAdmin, status_code=201)
def banners_criar(
    corpo: BannerCriar, sessao: Session = Depends(obter_sessao)
) -> BannerAdmin:
    return criar_banner(sessao, corpo)


# ANTES de /{bannerId}: "ordem" casaria com o parâmetro de caminho e morreria
# num 422 de "isto não é um inteiro".
@roteador_banners.patch("/ordem", response_model=list[BannerAdmin])
def banners_reordenar(
    corpo: OrdemBanners, sessao: Session = Depends(obter_sessao)
) -> list[BannerAdmin]:
    return reordenar_banners(sessao, corpo.ids)


@roteador_banners.patch("/{bannerId}", response_model=BannerAdmin)
def banners_editar(
    corpo: BannerEditar,
    banner_id: int = Path(alias="bannerId"),
    sessao: Session = Depends(obter_sessao),
) -> BannerAdmin:
    return editar_banner(sessao, banner_id, corpo)


@roteador_banners.delete("/{bannerId}", response_model=list[BannerAdmin])
def banners_excluir(
    banner_id: int = Path(alias="bannerId"), sessao: Session = Depends(obter_sessao)
) -> list[BannerAdmin]:
    """Devolve os que sobraram, renumerados — a tela mostra a ordem nova sem
    outra chamada."""
    return excluir_banner(sessao, banner_id)
