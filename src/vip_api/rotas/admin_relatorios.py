"""Destaques e consultas do painel (tarefas 58 e 60).

Quatro roteadores, todos incluídos no roteador protegido de admin_painel.py —
nenhum tem proteção própria e nenhum é exceção da varredura.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from vip_api.banco import obter_sessao
from vip_api.esquemas.admin_relatorios import (
    ClienteAdmin,
    DestaquesEntrada,
    Resumo,
)
from vip_api.esquemas.base import Pagina
from vip_api.servicos.admin_destaques import (
    definir_categorias_destaque,
    definir_produtos_destaque,
)
from vip_api.servicos.admin_relatorios import (
    POR_PAGINA_MAXIMO,
    POR_PAGINA_PADRAO,
    listar_clientes,
    montar_resumo,
)

roteador_destaques = APIRouter(prefix="/destaques", tags=["admin"])
roteador_resumo = APIRouter(tags=["admin"])
roteador_clientes = APIRouter(prefix="/clientes", tags=["admin"])


@roteador_destaques.patch("/produtos", response_model=list[int])
def destaques_produtos(
    corpo: DestaquesEntrada, sessao: Session = Depends(obter_sessao)
) -> list[int]:
    """SUBSTITUI o conjunto: quem está na lista vira destaque na ordem da
    posição, quem não está deixa de ser. Devolve os ids na ordem gravada."""
    return definir_produtos_destaque(sessao, corpo.ids)


@roteador_destaques.patch("/categorias", response_model=list[int])
def destaques_categorias(
    corpo: DestaquesEntrada, sessao: Session = Depends(obter_sessao)
) -> list[int]:
    return definir_categorias_destaque(sessao, corpo.ids)


@roteador_resumo.get("/resumo", response_model=Resumo)
def resumo(sessao: Session = Depends(obter_sessao)) -> Resumo:
    return montar_resumo(sessao)


@roteador_clientes.get("", response_model=Pagina[ClienteAdmin])
def clientes_listar(
    sessao: Session = Depends(obter_sessao),
    busca: str | None = Query(None, description="Parte do e-mail ou do nome."),
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(POR_PAGINA_PADRAO, alias="porPagina"),
) -> Pagina[ClienteAdmin]:
    return listar_clientes(sessao, busca, pagina, por_pagina)
